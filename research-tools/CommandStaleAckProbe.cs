// Two identical read-only COMMAND_INT requests with controlled ACK relay.
using System;
using System.Threading;
using MissionPlanner;
using MissionPlanner.Comms;
public static class CommandStaleAckProbe
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
            bool first = port.doCommandInt(1, 1, MAVLink.MAV_CMD.GET_MESSAGE_INTERVAL, 30, 0, 0, 0, 0, 0, 0, true);
            Console.WriteLine("FIRST_RESULT=" + first);
            Thread.Sleep(500);
            Console.WriteLine("BEFORE_SECOND_AVAILABLE=" + port.BaseStream.BytesToRead);
            bool second = port.doCommandInt(1, 1, MAVLink.MAV_CMD.GET_MESSAGE_INTERVAL, 30, 0, 0, 0, 0, 0, 0, true);
            Console.WriteLine("SECOND_RESULT=" + second);
            Thread.Sleep(1500);
            if (first || !second) throw new InvalidOperationException("unexpected test result");
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
