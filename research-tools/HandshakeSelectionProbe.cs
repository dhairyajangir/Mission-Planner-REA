// Timed synthetic heartbeats through the distributed Open() path; no socket or physical serial device.
using System;
using System.IO;
using System.Linq;
using System.Threading;
using MissionPlanner;
using MissionPlanner.Comms;

public sealed class TimedHeartbeatSerial : ICommsSerial
{
    readonly byte[][] frames;
    readonly object gate = new object();
    int frameIndex, offset;
    DateTime next = DateTime.UtcNow;
    public TimedHeartbeatSerial(byte[] bytes)
    {
        if (bytes.Length != 51) throw new ArgumentException("three heartbeat frames required");
        frames = Enumerable.Range(0, 3).Select(i => bytes.Skip(i * 17).Take(17).ToArray()).ToArray();
        ReadTimeout = 1000;
    }
    public Stream BaseStream { get { return Stream.Null; } }
    public int BytesToRead { get { lock (gate) return IsOpen && DateTime.UtcNow >= next ? 17 - offset : 0; } }
    public int BytesToWrite { get { return 0; } }
    public int BaudRate { get; set; } public int DataBits { get; set; }
    public bool DtrEnable { get; set; } public bool RtsEnable { get; set; }
    public bool IsOpen { get; private set; } public string PortName { get; set; }
    public int ReadBufferSize { get; set; } public int WriteBufferSize { get; set; }
    public int ReadTimeout { get; set; } public int WriteTimeout { get; set; }
    public int Writes { get; private set; }
    public void Open() { lock (gate) { IsOpen = true; next = DateTime.UtcNow.AddMilliseconds(100); } }
    public void Close() { lock (gate) IsOpen = false; }
    public void Dispose() { Close(); } public void toggleDTR() { }
    // Frames are scheduled after Open rather than representing old OS-buffered bytes.
    public void DiscardInBuffer() { }
    public int Read(byte[] buffer, int destination, int count)
    {
        var deadline = DateTime.UtcNow.AddMilliseconds(ReadTimeout > 0 ? ReadTimeout : 1000);
        while (DateTime.UtcNow < deadline)
        {
            lock (gate)
            {
                if (!IsOpen) throw new IOException("test transport closed");
                if (DateTime.UtcNow >= next)
                {
                    int n = Math.Min(count, 17 - offset);
                    Array.Copy(frames[frameIndex], offset, buffer, destination, n);
                    offset += n;
                    if (offset == 17) { offset = 0; frameIndex = (frameIndex + 1) % frames.Length; next = DateTime.UtcNow.AddMilliseconds(150); }
                    return n;
                }
            }
            Thread.Sleep(5);
        }
        throw new TimeoutException("test transport read timeout");
    }
    public int ReadByte() { var b = new byte[1]; Read(b, 0, 1); return b[0]; }
    public int ReadChar() { return ReadByte(); }
    public string ReadExisting() { throw new NotSupportedException(); }
    public string ReadLine() { throw new NotSupportedException(); }
    public void Write(byte[] buffer, int start, int count) { Writes++; }
    public void Write(string value) { Writes++; } public void WriteLine(string value) { Writes++; }
}

public static class HandshakeSelectionProbe
{
    public static int Main(string[] args)
    {
        var port = new MAVLinkInterface();
        try
        {
            log4net.Config.BasicConfigurator.Configure();
            var serial = new TimedHeartbeatSerial(File.ReadAllBytes(args[0]));
            port.BaseStream = serial;
            port.Open(false, false, false);
            Console.WriteLine("OPEN=" + serial.IsOpen + " SELECTED=" + port.sysidcurrent + ":" + port.compidcurrent +
                              " VISIBLE=" + port.MAVlist.Count + " WRITES=" + serial.Writes);
            Console.WriteLine("VISIBLE_LIST=" + String.Join(",", port.MAVlist.Select(x => x.sysid + ":" + x.compid + ":" + x.aptype).OrderBy(x => x).ToArray()));
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
        finally { port.Close(); }
    }
}
