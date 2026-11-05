// Original command methods against disposable SITL with an unsupported command ID.
using System;
using MissionPlanner;
using MissionPlanner.Comms;
public static class UnsupportedCommandProbe
{
    public static int Main(string[] args)
    {
        MAVLinkInterface port = null;
        try
        {
            log4net.Config.BasicConfigurator.Configure();
            port = new MAVLinkInterface { BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[0] } };
            port.Open(false, false, false);
            Console.WriteLine("OPEN=" + port.BaseStream.IsOpen + " SELECTED=" + port.sysidcurrent + ":" + port.compidcurrent);
            var unknown = (MAVLink.MAV_CMD)65530;
            bool first = port.doCommand(1, 1, unknown, 0, 0, 0, 0, 0, 0, 0, true);
            Console.WriteLine("LONG_RESULT=" + first);
            bool second = port.doCommandInt(1, 1, unknown, 0, 0, 0, 0, 0, 0, 0, true);
            Console.WriteLine("INT_RESULT=" + second);
            if (first || second) throw new InvalidOperationException("unexpected accepted unsupported command");
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
