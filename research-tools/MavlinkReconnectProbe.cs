// Original Mission Planner library, disposable SITL through a test-controlled TCP relay.
using System;
using System.IO;
using System.Threading;
using MissionPlanner;
using MissionPlanner.Comms;
public static class MavlinkReconnectProbe
{
    public static int Main(string[] args)
    {
        MAVLinkInterface port = null;
        try
        {
            log4net.Config.BasicConfigurator.Configure();
            var tcp = new TcpSerial { Host = "127.0.0.1", Port = args[0] };
            port = new MAVLinkInterface { BaseStream = tcp };
            port.Open(false, false, false);
            Console.WriteLine("FIRST_OPEN=" + tcp.IsOpen + " SELECTED=" + port.sysidcurrent + ":" + port.compidcurrent);
            float before = port.GetParam(1, 1, "LOG_DISARMED");
            Console.WriteLine("FIRST_PARAM=" + before);
            File.WriteAllText(Path.Combine(args[1], "drop.request"), "drop first session\n");
            var deadline = DateTime.UtcNow.AddSeconds(20);
            while (!File.Exists(Path.Combine(args[1], "drop.ack")) && DateTime.UtcNow < deadline) Thread.Sleep(100);
            if (!File.Exists(Path.Combine(args[1], "drop.ack"))) throw new TimeoutException("drop acknowledgement");
            Console.WriteLine("AFTER_DROP_BEFORE_CLOSE_OPEN=" + tcp.IsOpen);
            port.Close();
            tcp.Host = "127.0.0.1";
            port.Open(false, false, false);
            Console.WriteLine("SECOND_OPEN=" + tcp.IsOpen + " SELECTED=" + port.sysidcurrent + ":" + port.compidcurrent);
            float after = port.GetParam(1, 1, "LOG_DISARMED");
            Console.WriteLine("SECOND_PARAM=" + after);
            if (!tcp.IsOpen || before != 0 || after != 0 || port.sysidcurrent != 1 || port.compidcurrent != 1)
                throw new InvalidOperationException("unexpected reconnect result");
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
