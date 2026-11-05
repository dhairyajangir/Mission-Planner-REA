// Calls the distributed communication library with local simulator-derived log fixtures.
using System;
using System.IO;
using System.Reflection;
using MissionPlanner;

public static class TlogPlaybackProbe
{
    public static int Main(string[] args)
    {
        try
        {
            log4net.Config.BasicConfigurator.Configure();
            foreach (string path in args)
            {
                Console.WriteLine("FIXTURE=" + Path.GetFileName(path));
                Run(path, true);
                Run(path, false);
            }
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
    }
    static void Run(string path, bool direct)
    {
        var port = new MAVLinkInterface();
        using (var stream = File.OpenRead(path))
        using (var reader = new BinaryReader(stream))
        {
            port.logplaybackfile = reader;
            port.logreadmode = true;
            var message = direct
                ? (MAVLink.MAVLinkMessage)typeof(MAVLinkInterface).GetMethod("readlogPacketMavlink", BindingFlags.NonPublic | BindingFlags.Instance).Invoke(port, null)
                : port.readPacket();
            Console.WriteLine((direct ? "DIRECT" : "VALIDATED") +
                " LENGTH=" + (message.buffer == null ? 0 : message.buffer.Length) +
                " MESSAGE=" + message.msgid + " SYSTEM=" + message.sysid +
                " POSITION=" + stream.Position + " FILE_LENGTH=" + stream.Length +
                " HEX=" + (message.buffer == null ? "" : BitConverter.ToString(message.buffer).Replace("-", "")));
        }
    }
}
