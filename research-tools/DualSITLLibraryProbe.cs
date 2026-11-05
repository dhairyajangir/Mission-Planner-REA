// Original Mission Planner library against two disposable localhost SITL instances via a local relay.
using System;
using System.Linq;
using System.Threading;
using MissionPlanner;
using MissionPlanner.Comms;

public static class DualSITLLibraryProbe
{
    public static int Main(string[] args)
    {
        MAVLinkInterface port = null;
        try
        {
            log4net.Config.BasicConfigurator.Configure();
            port = new MAVLinkInterface();
            port.BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[0] };
            port.Open(false, false, false);
            Console.WriteLine("OPEN=" + port.BaseStream.IsOpen + " INITIAL=" + port.sysidcurrent + ":" + port.compidcurrent);
            if (!port.BaseStream.IsOpen) throw new InvalidOperationException("relay connection not open");
            var deadline = DateTime.UtcNow.AddSeconds(15);
            while (DateTime.UtcNow < deadline && (!port.MAVlist.Contains(1, 1, false) || !port.MAVlist.Contains(2, 1, false)))
                port.readPacket();
            Console.WriteLine("SEEN_1=" + port.MAVlist.Contains(1, 1, false) + " SEEN_2=" + port.MAVlist.Contains(2, 1, false) +
                              " VISIBLE=" + port.MAVlist.Count);
            Console.WriteLine("VISIBLE_LIST=" + String.Join(",", port.MAVlist.Select(x => x.sysid + ":" + x.compid).OrderBy(x => x).ToArray()));
            if (!port.MAVlist.Contains(1, 1, false) || !port.MAVlist.Contains(2, 1, false))
                throw new InvalidOperationException("both simulator systems were not discovered");
            float one = port.GetParam(1, 1, "LOG_DISARMED");
            float two = port.GetParam(2, 1, "LOG_DISARMED");
            Console.WriteLine("DIRECT_1=" + one + " DIRECT_2=" + two);
            port.sysidcurrent = 1; port.compidcurrent = 1;
            float selectedOne = port.GetParam("LOG_DISARMED");
            port.sysidcurrent = 2; port.compidcurrent = 1;
            float selectedTwo = port.GetParam("LOG_DISARMED");
            Console.WriteLine("SELECTED_1=" + selectedOne + " SELECTED_2=" + selectedTwo);
            Console.WriteLine("CACHE_1=" + port.MAVlist[1, 1].param["LOG_DISARMED"].Value +
                              " CACHE_2=" + port.MAVlist[2, 1].param["LOG_DISARMED"].Value);
            bool restored = port.setParam(2, 1, "LOG_DISARMED", 0, true);
            float after = port.GetParam(2, 1, "LOG_DISARMED");
            Console.WriteLine("RESTORE_2=" + restored + " READBACK_2=" + after);
            if (one != 0 || two != 1 || selectedOne != 0 || selectedTwo != 1 || !restored || after != 0)
                throw new InvalidOperationException("unexpected dual-simulator parameter result");
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
