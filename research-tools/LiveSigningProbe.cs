// Test-only memory transport. No network or operating-system serial device is opened.
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using MissionPlanner;
using MissionPlanner.Comms;

public sealed class MemorySerial : ICommsSerial
{
    readonly MemoryStream input;
    public MemorySerial(byte[] data) { input = new MemoryStream(data); IsOpen = true; ReadTimeout = 500; }
    public Stream BaseStream { get { return input; } }
    public int BytesToRead { get { return (int)(input.Length - input.Position); } }
    public int BytesToWrite { get { return 0; } }
    public int BaudRate { get; set; } public int DataBits { get; set; }
    public bool DtrEnable { get; set; } public bool RtsEnable { get; set; }
    public bool IsOpen { get; private set; } public string PortName { get; set; }
    public int ReadBufferSize { get; set; } public int WriteBufferSize { get; set; }
    public int ReadTimeout { get; set; } public int WriteTimeout { get; set; }
    public void Open() { IsOpen = true; } public void Close() { IsOpen = false; }
    public void Dispose() { Close(); input.Dispose(); } public void toggleDTR() { }
    public void DiscardInBuffer() { input.Position = input.Length; }
    public int Read(byte[] buffer, int offset, int count) { return input.Read(buffer, offset, count); }
    public int ReadByte() { int b = input.ReadByte(); if (b < 0) throw new TimeoutException(); return b; }
    public int ReadChar() { return ReadByte(); }
    public string ReadExisting() { throw new NotSupportedException(); }
    public string ReadLine() { throw new NotSupportedException(); }
    public void Write(byte[] buffer, int offset, int count) { }
    public void Write(string value) { } public void WriteLine(string value) { }
}

public static class LiveSigningProbe
{
    static readonly byte[] TestKey = Enumerable.Range(0, 32).Select(x => (byte)x).ToArray();
    static void Run(string name, byte[] frame, bool useKey, bool ignore, bool signing, int reads)
    {
        var port = new MAVLinkInterface();
        var serial = new MemorySerial(frame);
        port.BaseStream = serial;
        var state = port.MAVlist[1, 1];
        state.signingignore = ignore;
        state.signing = signing;
        if (useKey)
            typeof(MAVState).GetField("signingKey", BindingFlags.Instance | BindingFlags.NonPublic).SetValue(state, TestKey);
        Console.WriteLine("CASE=" + name + " KEY=" + useKey + " IGNORE=" + ignore + " SIGNING=" + signing);
        for (int i = 0; i < reads; i++)
        {
            var packet = port.readPacket();
            Console.WriteLine("READ=" + i + " LENGTH=" + (packet.buffer == null ? 0 : packet.buffer.Length) +
                " SYSTEM=" + packet.sysid + " COMPONENT=" + packet.compid + " REMAINING=" + serial.BytesToRead +
                " STATE_SIGNING=" + state.signing);
        }
        serial.Dispose();
    }
    public static int Main(string[] args)
    {
        try
        {
            log4net.Config.BasicConfigurator.Configure();
            var root = args[0];
            var signed = File.ReadAllBytes(Path.Combine(root, "signed.bin"));
            var bad = File.ReadAllBytes(Path.Combine(root, "bad-signature.bin"));
            var twice = File.ReadAllBytes(Path.Combine(root, "signed-twice.bin"));
            var unsigned = File.ReadAllBytes(Path.Combine(root, "unsigned.bin"));
            var signedThenUnsigned = File.ReadAllBytes(Path.Combine(root, "signed-then-unsigned.bin"));
            Run("valid-key", signed, true, false, false, 1);
            Run("bad-signature", bad, true, false, false, 1);
            Run("ignore-bad", bad, true, true, false, 1);
            Run("same-signed-twice", twice, true, false, false, 2);
            Run("unsigned-while-signing", unsigned, true, false, true, 1);
            Run("signed-then-unsigned", signedThenUnsigned, true, false, false, 2);
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
    }
}
