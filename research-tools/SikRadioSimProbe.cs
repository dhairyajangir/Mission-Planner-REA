// Drives Mission Planner 1.3.83's SiK radio configuration code (MissionPlanner.Radio.Sikradio.doCommand / doConnect) from
// the original MissionPlanner.exe against a SIMULATED radio implemented in this file. No radio hardware, no real serial port.
// The simulation is a minimal model written from the code's own expectations (echo of each command, "OK" after +++); it is
// not a model of real SiK firmware, so results show how the library reacts to those replies, not how a radio behaves.
// Usage: SikRadioSimProbe.exe <isolated dir> <out dir>
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using MissionPlanner.Comms;

public enum Behaviour { Normal, NoEcho, Silent, RfdStyleVersion, NoPlusPlusPlusOk, Garbage }

public sealed class SimRadio : ICommsSerial
{
    readonly Queue<byte> outq = new Queue<byte>();
    readonly StringBuilder inbuf = new StringBuilder();
    public readonly List<string> Received = new List<string>();
    public Behaviour Mode = Behaviour.Normal;
    public bool InCommandMode;
    public bool IsOpen { get { return true; } }
    public Stream BaseStream { get { return Stream.Null; } }
    public int BaudRate { get; set; }
    public int BytesToRead { get { lock (outq) return outq.Count; } }
    public int BytesToWrite { get { return 0; } }
    public int DataBits { get; set; }
    public bool DtrEnable { get; set; }
    public string PortName { get; set; }
    public int ReadBufferSize { get; set; }
    public int ReadTimeout { get; set; }
    public bool RtsEnable { get; set; }
    public int WriteBufferSize { get; set; }
    public int WriteTimeout { get; set; }
    public void Open() { }
    public void Close() { }
    public void Dispose() { }
    public void DiscardInBuffer() { lock (outq) outq.Clear(); }
    void Queue(string s) { lock (outq) foreach (var b in Encoding.ASCII.GetBytes(s)) outq.Enqueue(b); }
    public int Read(byte[] buffer, int offset, int count)
    {
        int n = 0;
        lock (outq) while (n < count && outq.Count > 0) buffer[offset + n++] = outq.Dequeue();
        if (n == 0) throw new TimeoutException("sim: no data");
        return n;
    }
    public int ReadByte() { lock (outq) return outq.Count > 0 ? outq.Dequeue() : -1; }
    public int ReadChar() { return ReadByte(); }
    public string ReadExisting() { lock (outq) { var s = Encoding.ASCII.GetString(outq.ToArray()); outq.Clear(); return s; } }
    public string ReadLine() { var sb = new StringBuilder(); int b; while ((b = ReadByte()) >= 0) { sb.Append((char)b); if (b == '\n') break; } return sb.ToString(); }
    public void Write(string text) { Write(Encoding.ASCII.GetBytes(text), 0, text.Length); }
    public void Write(byte[] buffer, int offset, int count) { lock (inbuf) { inbuf.Append(Encoding.ASCII.GetString(buffer, offset, count)); Process(); } }
    public void WriteLine(string text) { Write(text + "\r\n"); }
    public void toggleDTR() { }

    void Process()
    {
        if (Mode == Behaviour.Silent) { inbuf.Clear(); return; }
        string s = inbuf.ToString();
        if (s.EndsWith("+++") && !s.Contains("\n"))
        {
            Received.Add("+++");
            inbuf.Clear();
            if (Mode != Behaviour.NoPlusPlusPlusOk) { InCommandMode = true; Queue("OK\r\n"); }
            return;
        }
        int nl;
        while ((nl = inbuf.ToString().IndexOf('\n')) >= 0)
        {
            string line = inbuf.ToString(0, nl).Trim('\r', '\n', ' ');
            inbuf.Remove(0, nl + 1);
            if (line.Length == 0) { Queue("\r\n"); continue; }
            Received.Add(line);
            if (Mode != Behaviour.NoEcho) Queue(line + "\r\n");
            Queue(Reply(line) + "\r\n");
        }
    }

    string Reply(string cmd)
    {
        if (Mode == Behaviour.Garbage) return "\u0001\u0002???";
        switch (cmd)
        {
            case "ATO": InCommandMode = false; return "";
            case "AT&T": return "OK";
            case "ATI": return Mode == Behaviour.RfdStyleVersion ? "RFD900x V3.1 on RFD900X" : "SiK 1.9 on HM-TRP";
            case "ATI2": return "133";
            case "ATI3": return "27";
            case "ATI5": return "S0:FORMAT=26\r\nS1:SERIAL_SPEED=57\r\nS2:AIR_SPEED=64\r\nS3:NETID=25\r\nS4:TXPOWER=20";
            case "ATI7": return "L/R RSSI: 200/190  L/R noise: 50/48 pkts: 100  txe=0 rxe=0 stx=0 srx=0 ecc=0/0 temp=30 dco=0";
            case "AT&W": return "OK";
            case "ATZ": return "";
            default: return "ERROR";
        }
    }
}

public static class SikRadioSimProbe
{
    public static int Main(string[] args)
    {
        string dir = Path.GetFullPath(args[0]);
        AppDomain.CurrentDomain.AssemblyResolve += (s, e) =>
        {
            string n = new AssemblyName(e.Name).Name;
            string p = Path.Combine(dir, n + ".dll");
            if (!File.Exists(p)) p = Path.Combine(dir, n + ".exe");
            return File.Exists(p) ? Assembly.LoadFrom(p) : null;
        };
        Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
        Application.ThreadException += (s, e) => Console.WriteLine("THREAD-EXCEPTION " + e.Exception.GetType().Name + ": " + e.Exception.Message);
        int rc = 1;
        var th = new Thread(() => rc = Run(dir, Path.GetFullPath(args[1])));
        th.SetApartmentState(ApartmentState.STA);
        th.Start();
        th.Join(600000);
        Environment.Exit(rc);
        return rc;
    }

    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
    static int Run(string dir, string outDir)
    {
        try
        {
            Directory.CreateDirectory(outDir);
            var asm = Assembly.LoadFrom(Path.Combine(dir, "MissionPlanner.exe"));
            var type = asm.GetType("MissionPlanner.Radio.Sikradio");
            var page = Activator.CreateInstance(type);
            var doCommand = type.GetMethod("doCommand");
            var doConnect = type.GetMethod("doConnect");
            var csv = new StringBuilder("case,behaviour,call,result,elapsed_ms,commands_seen_by_radio\n");
            Func<string, Behaviour, string, Func<SimRadio, object>, bool> run = (name, mode, call, f) =>
            {
                var sim = new SimRadio { Mode = mode, ReadTimeout = 1000 };
                var sw = System.Diagnostics.Stopwatch.StartNew();
                string result;
                try { result = Convert.ToString(f(sim)); }
                catch (Exception ex) { var i = ex; while (i.InnerException != null) i = i.InnerException; result = "EXCEPTION " + i.GetType().Name + ": " + i.Message; }
                csv.AppendFormat("{0},{1},{2},\"{3}\",{4},\"{5}\"\n", name, mode, call, result.Replace("\"", "'").Replace("\r", "\\r").Replace("\n", "\\n"), sw.ElapsedMilliseconds,
                    string.Join(" | ", sim.Received));
                Console.WriteLine("{0,-26} {1,-18} {2,-14} {3} ({4} ms)", name, mode, call, result.Length > 70 ? result.Substring(0, 70) : result, sw.ElapsedMilliseconds);
                return true;
            };
            run("ati-normal", Behaviour.Normal, "doCommand ATI", s => doCommand.Invoke(page, new object[] { s, "ATI", false, 0 }));
            run("ati5-multiline", Behaviour.Normal, "doCommand ATI5", s => doCommand.Invoke(page, new object[] { s, "ATI5", true, 0 }));
            run("ati7-rssi", Behaviour.Normal, "doCommand ATI7", s => doCommand.Invoke(page, new object[] { s, "ATI7", false, 0 }));
            run("unknown-command", Behaviour.Normal, "doCommand ATX", s => doCommand.Invoke(page, new object[] { s, "ATX", false, 0 }));
            run("no-echo", Behaviour.NoEcho, "doCommand ATI", s => doCommand.Invoke(page, new object[] { s, "ATI", false, 0 }));
            run("silent-radio", Behaviour.Silent, "doCommand ATI", s => doCommand.Invoke(page, new object[] { s, "ATI", false, 0 }));
            run("garbage-reply", Behaviour.Garbage, "doCommand ATI", s => doCommand.Invoke(page, new object[] { s, "ATI", false, 0 }));
            run("connect-normal", Behaviour.Normal, "doConnect", s => doConnect.Invoke(page, new object[] { s }));
            run("connect-rfd-style-version", Behaviour.RfdStyleVersion, "doConnect", s => doConnect.Invoke(page, new object[] { s }));
            run("connect-no-ok-after-+++", Behaviour.NoPlusPlusPlusOk, "doConnect", s => doConnect.Invoke(page, new object[] { s }));
            run("connect-silent", Behaviour.Silent, "doConnect", s => doConnect.Invoke(page, new object[] { s }));
            File.WriteAllText(Path.Combine(outDir, "sikradio-sim.csv"), csv.ToString().Replace("\r\n", "\n"), new UTF8Encoding(false));
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
    }
}
