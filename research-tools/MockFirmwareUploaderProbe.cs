// Test-only in-memory bootloader protocol. No operating-system serial device is opened.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using MissionPlanner.Comms;
using px4uploader;

public sealed class MockBootloader : ICommsSerial
{
    readonly Queue<byte> input = new Queue<byte>();
    readonly List<byte> program = new List<byte>();
    bool receivingProgram;
    int expected;
    public bool Erased { get; private set; }
    public bool Rebooted { get; private set; }
    public bool FailErase { get; set; }
    public bool CorruptVerification { get; set; }
    public int VerifySize { get; set; }
    public int BootloaderRevision { get; set; }
    public int Writes { get; private set; }
    public byte[] Programmed { get { return program.ToArray(); } }
    public Stream BaseStream { get { return Stream.Null; } }
    public int BaudRate { get; set; }
    public int BytesToRead { get { return input.Count; } }
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
    public void Open() { IsOpen = true; }
    public void Close() { IsOpen = false; }
    public void Dispose() { Close(); }
    public void DiscardInBuffer() { input.Clear(); }
    public void toggleDTR() { }
    public int Read(byte[] b, int offset, int count)
    {
        if (input.Count == 0) throw new TimeoutException("mock input empty");
        int n = Math.Min(count, input.Count);
        for (int i = 0; i < n; i++) b[offset + i] = input.Dequeue();
        return n;
    }
    public int ReadByte() { var b = new byte[1]; Read(b, 0, 1); return b[0]; }
    public int ReadChar() { return ReadByte(); }
    public string ReadExisting() { throw new NotSupportedException(); }
    public string ReadLine() { throw new NotSupportedException(); }
    public void Write(string value) { var data = Encoding.ASCII.GetBytes(value); Write(data, 0, data.Length); }
    public void WriteLine(string value) { Write(value + "\n"); }
    void Sync() { input.Enqueue(0x12); input.Enqueue(0x10); }
    public void Write(byte[] buffer, int offset, int count)
    {
        Writes++;
        byte[] data = buffer.Skip(offset).Take(count).ToArray();
        if (receivingProgram)
        {
            if (expected > 0)
            {
                if (data.Length != expected) throw new InvalidDataException("unexpected payload size");
                program.AddRange(data); expected = 0; return;
            }
            if (data.Length != 1 || data[0] != 0x20) throw new InvalidDataException("missing program EOC");
            receivingProgram = false; Sync(); return;
        }
        if (data.Length == 2 && data[0] == 0x21 && data[1] == 0x20) { Sync(); return; }
        if (data.Length == 3 && data[0] == 0x22 && data[1] == 1 && data[2] == 0x20)
        { foreach (byte b in BitConverter.GetBytes(BootloaderRevision)) input.Enqueue(b); Sync(); return; }
        if (data.Length == 2 && data[0] == 0x23 && data[1] == 0x20)
        {
            Erased = true;
            if (FailErase) { input.Enqueue(0x12); input.Enqueue(0x11); }
            else Sync();
            return;
        }
        if (data.Length == 2 && data[0] == 0x27) { expected = data[1]; receivingProgram = true; return; }
        if (data.Length == 2 && data[0] == 0x24 && data[1] == 0x20) { Sync(); return; }
        if (data.Length == 2 && data[0] == 0x29 && data[1] == 0x20)
        {
            uint crc = 0;
            var bytes = program.Concat(Enumerable.Repeat((byte)0xff, Math.Max(0, VerifySize - program.Count)));
            foreach (byte b in bytes)
            {
                crc ^= b;
                for (int bit = 0; bit < 8; bit++)
                    crc = (crc >> 1) ^ ((crc & 1) != 0 ? 0xedb88320U : 0U);
            }
            if (CorruptVerification) crc ^= 1;
            foreach (byte b in BitConverter.GetBytes(crc)) input.Enqueue(b);
            Sync(); return;
        }
        if (data.Length == 3 && data[0] == 0x28 && data[2] == 0x20)
        {
            if (data[1] != program.Count) throw new InvalidDataException("unexpected mock read size");
            for (int i = 0; i < program.Count; i++)
                input.Enqueue((byte)(program[i] ^ (CorruptVerification && i == 0 ? 1 : 0)));
            Sync(); return;
        }
        if (data.Length == 2 && data[0] == 0x30 && data[1] == 0x20) { Rebooted = true; return; }
        throw new InvalidDataException("unexpected mock command " + BitConverter.ToString(data));
    }
}

public static class MockFirmwareUploaderProbe
{
    public static int Main(string[] args)
    {
        foreach (string path in args)
        {
            var fw = Firmware.ProcessFirmware(path);
            bool crcCases = Environment.GetEnvironmentVariable("MOCK_CRC_CASES") == "1";
            var modes = crcCases ? new[] {"crc-mismatch", "crc-matching"}
                : Environment.GetEnvironmentVariable("MOCK_FAULT_CASES") == "1"
                    ? new[] {"erase-failure", "verify-mismatch", "matching"}
                    : new[] {"mismatch", "too-small", "matching"};
            foreach (string mode in modes)
            {
                var port = new MockBootloader();
                port.FailErase = mode == "erase-failure";
                port.CorruptVerification = mode == "verify-mismatch" || mode == "crc-mismatch";
                port.VerifySize = 512;
                port.BootloaderRevision = crcCases ? 3 : 2;
                var uploader = new Uploader(port);
                uploader.board_type = mode == "mismatch" ? fw.board_id + 1 : fw.board_id;
                uploader.fw_maxsize = mode == "too-small" ? fw.image_size - 1 : 512;
                uploader.bl_rev = crcCases ? 3 : 2;
                string status = "OK";
                try { uploader.upload(fw); }
                catch (Exception ex) { status = ex.GetType().Name + ":" + ex.Message; }
                string outputDir = Environment.GetEnvironmentVariable("MOCK_UPLOADER_OUTPUT");
                if (mode == "matching" && !String.IsNullOrEmpty(outputDir))
                    File.WriteAllBytes(Path.Combine(outputDir, Path.GetFileName(path) + ".programmed.bin"), port.Programmed);
                Console.WriteLine("RESULT|" + Path.GetFileName(path) + "|" + mode + "|" + status +
                                  "|writes=" + port.Writes + "|erased=" + port.Erased +
                                  "|rebooted=" + port.Rebooted + "|bytes=" + port.Programmed.Length +
                                  "|tail=" + BitConverter.ToString(port.Programmed.Skip(Math.Max(0, port.Programmed.Length - 8)).ToArray()).Replace("-", ""));
                uploader.Dispose();
            }
        }
        return 0;
    }
}
