// Observe library playback timestamps without running the GUI playback scheduler.
using System;
using System.IO;
using MissionPlanner;

public static class TlogTimestampProbe
{
    public static int Main(string[] args)
    {
        try
        {
            log4net.Config.BasicConfigurator.Configure();
            foreach (string path in args)
            {
                Console.WriteLine("FIXTURE=" + Path.GetFileName(path));
                var port = new MAVLinkInterface();
                using (var stream = File.OpenRead(path))
                using (var reader = new BinaryReader(stream))
                {
                    port.logplaybackfile = reader;
                    port.logreadmode = true;
                    for (int i = 0; i < 2 && stream.Position < stream.Length; i++)
                    {
                        var packet = port.readPacket();
                        Console.WriteLine("READ=" + i + " POSITION=" + stream.Position +
                            " LENGTH=" + (packet.buffer == null ? 0 : packet.buffer.Length) +
                            " UTC=" + port.lastlogread.ToUniversalTime().ToString("o"));
                    }
                }
            }
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
    }
}
