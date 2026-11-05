// Test-only, file-backed ICommsSerial. A separate local-only relay translates
// these byte streams to the disposable SITL TCP listener. No external network.
using System;
using System.IO;
using System.Text;
using System.Threading;
using MissionPlanner.Comms;

namespace MissionPlannerTest
{
public sealed class FileSpoolSerial : ICommsSerial
{
    private readonly string directory;
    private FileStream input;
    private FileStream output;
    private readonly object readLock = new object();
    private readonly object writeLock = new object();
    public FileSpoolSerial(string directory) { this.directory = directory; ReadTimeout = 1000; }
    public Stream BaseStream { get { return Stream.Null; } }
    public int BaudRate { get; set; }
    public int BytesToRead { get { lock (readLock) return input == null ? 0 : (int)Math.Min(int.MaxValue, Math.Max(0, input.Length - input.Position)); } }
    public int BytesToWrite { get { return 0; } }
    public int DataBits { get; set; }
    public bool DtrEnable { get; set; }
    public bool IsOpen { get; private set; }
    public string PortName { get; set; }
    public int ReadBufferSize { get; set; }
    public int ReadTimeout { get; set; }
    public bool RtsEnable { get; set; }
    public int WriteBufferSize { get; set; }
    public int WriteTimeout { get; set; }

    public void Open()
    {
        Directory.CreateDirectory(directory);
        input = new FileStream(Path.Combine(directory, "to-app.bin"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.ReadWrite);
        output = new FileStream(Path.Combine(directory, "from-app.bin"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.ReadWrite);
        output.Position = output.Length;
        IsOpen = true;
        File.WriteAllText(Path.Combine(directory, "ready.txt"), "ready\n");
    }
    public void Close()
    {
        IsOpen = false;
        lock (readLock) { if (input != null) input.Dispose(); input = null; }
        lock (writeLock) { if (output != null) output.Dispose(); output = null; }
        File.WriteAllText(Path.Combine(directory, "closed.txt"), "closed\n");
    }
    public void Dispose() { if (IsOpen) Close(); }
    public void DiscardInBuffer() { lock (readLock) if (input != null) input.Position = input.Length; }
    public int Read(byte[] buffer, int offset, int count)
    {
        var deadline = DateTime.UtcNow.AddMilliseconds(ReadTimeout > 0 ? ReadTimeout : 1000);
        do {
            lock (readLock) {
                if (!IsOpen || input == null) throw new IOException("Spool closed");
                if (input.Length > input.Position) return input.Read(buffer, offset, count);
            }
            Thread.Sleep(5);
        } while (DateTime.UtcNow < deadline);
        throw new TimeoutException("Spool read timeout");
    }
    public int ReadByte() { var b = new byte[1]; return Read(b, 0, 1) == 1 ? b[0] : -1; }
    public int ReadChar() { return ReadByte(); }
    public string ReadExisting() { var b = new byte[BytesToRead]; return b.Length == 0 ? "" : Encoding.ASCII.GetString(b, 0, Read(b, 0, b.Length)); }
    public string ReadLine() { var b = new StringBuilder(); while (b.Length < 4096) { int x = ReadByte(); if (x == 10) break; b.Append((char)x); } return b.ToString(); }
    public void Write(string text) { var b = Encoding.ASCII.GetBytes(text); Write(b, 0, b.Length); }
    public void Write(byte[] buffer, int offset, int count) { lock (writeLock) { if (!IsOpen || output == null) throw new IOException("Spool closed"); output.Write(buffer, offset, count); output.Flush(); } }
    public void WriteLine(string text) { Write(text + "\n"); }
    public void toggleDTR() { }
}
}
