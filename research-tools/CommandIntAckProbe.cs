// Original COMMAND_INT against disposable SITL, requesting message interval only.
using System;
using MissionPlanner;
using MissionPlanner.Comms;
public static class CommandIntAckProbe
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
            try
            {
                bool value = port.doCommandInt(1, 1, MAVLink.MAV_CMD.GET_MESSAGE_INTERVAL, 30, 0, 0, 0, 0, 0, 0, true);
                Console.WriteLine("COMMAND_RESULT=" + value);
                if (args[1] == "drop_all" || !value) return 2;
            }
            catch (TimeoutException ex)
            {
                Console.WriteLine("COMMAND_TIMEOUT=" + ex.Message);
                if (args[1] != "drop_all") return 3;
            }
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
