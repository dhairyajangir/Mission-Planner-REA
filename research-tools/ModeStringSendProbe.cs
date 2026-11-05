// String-based tracker mode selection; in-memory serial captures writes only.
using System;
using System.IO;
using MissionPlanner;
using MissionPlanner.ArduPilot;
using MissionPlanner.Comms;
public sealed class ModeCaptureSerial : ICommsSerial
{
    public readonly MemoryStream output = new MemoryStream();
    public Stream BaseStream { get { return output; } }
    public int BytesToRead { get { return 0; } } public int BytesToWrite { get { return 0; } }
    public int BaudRate { get; set; } public int DataBits { get; set; } public bool DtrEnable { get; set; }
    public bool RtsEnable { get; set; } public bool IsOpen { get; private set; }
    public ModeCaptureSerial() { IsOpen = true; }
    public string PortName { get; set; } public int ReadBufferSize { get; set; } public int WriteBufferSize { get; set; }
    public int ReadTimeout { get; set; } public int WriteTimeout { get; set; }
    public void Open() { IsOpen = true; } public void Close() { IsOpen = false; }
    public void Dispose() { Close(); output.Dispose(); } public void toggleDTR() { }
    public void DiscardInBuffer() { } public int Read(byte[] b, int o, int n) { return 0; }
    public int ReadByte() { throw new TimeoutException(); } public int ReadChar() { return ReadByte(); }
    public string ReadExisting() { return ""; } public string ReadLine() { throw new TimeoutException(); }
    public void Write(byte[] b, int o, int n) { output.Write(b, o, n); }
    public void Write(string s) { throw new NotSupportedException(); } public void WriteLine(string s) { throw new NotSupportedException(); }
}
public static class ModeStringSendProbe
{
    public static int Main(string[] args)
    {
        try
        {
            var serial = new ModeCaptureSerial();
            var port = new MAVLinkInterface { BaseStream = serial };
            port.sysidcurrent = 1; port.compidcurrent = 1;
            port.MAVlist[1, 1].cs.firmware = Firmwares.ArduTracker;
            port.setMode(1, 1, "not-a-mode");
            Console.WriteLine("INVALID_BYTES=" + serial.output.Length);
            if (serial.output.Length != 0) throw new InvalidOperationException("invalid mode sent bytes");
            port.setMode(1, 1, "sCaN");
            byte[] captured = serial.output.ToArray();
            File.WriteAllBytes(args[0], captured);
            Console.WriteLine("VALID_BYTES=" + captured.Length);
            if (captured.Length == 0) throw new InvalidOperationException("no valid mode packets");
            serial.Dispose();
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
    }
}
