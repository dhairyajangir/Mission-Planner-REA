// Original command methods; local relay inserts an IN_PROGRESS ACK before SITL's ACK.
using System;
using System.Threading;
using MissionPlanner;
using MissionPlanner.Comms;
public static class CommandProgressRelayProbe
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
            bool answer = args[1] == "long"
                ? port.doCommand(1, 1, MAVLink.MAV_CMD.GET_MESSAGE_INTERVAL, 30, 0, 0, 0, 0, 0, 0, true)
                : port.doCommandInt(1, 1, MAVLink.MAV_CMD.GET_MESSAGE_INTERVAL, 30, 0, 0, 0, 0, 0, 0, true);
            Console.WriteLine("FORM=" + args[1] + " RESULT=" + answer);
            Thread.Sleep(250);
            Console.WriteLine("BYTES_AFTER_RETURN=" + port.BaseStream.BytesToRead);
            if (answer != (args[1] == "long")) throw new InvalidOperationException("unexpected result");
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
