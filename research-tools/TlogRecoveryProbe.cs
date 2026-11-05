// Exercise sequential readPacket calls on finite local telemetry-log fixtures.
using System;
using System.IO;
using MissionPlanner;

public static class TlogRecoveryProbe
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
                    for (int i = 0; i < 4 && stream.Position < stream.Length; i++)
                    {
                        long before = stream.Position;
                        var result = port.readPacket();
                        Console.WriteLine("READ=" + i + " BEFORE=" + before + " AFTER=" + stream.Position +
                            " SIZE=" + stream.Length + " LENGTH=" + (result.buffer == null ? 0 : result.buffer.Length) +
                            " MESSAGE=" + result.msgid + " SYSTEM=" + result.sysid);
                        if (stream.Position <= before) break;
                    }
                }
            }
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
    }
}
