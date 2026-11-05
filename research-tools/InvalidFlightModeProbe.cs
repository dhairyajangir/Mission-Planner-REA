// Original library; invalid numeric mode against disposable disarmed Copter SITL.
using System;
using MissionPlanner;
using MissionPlanner.Comms;
public static class InvalidFlightModeProbe
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
            var initialDeadline = DateTime.UtcNow.AddSeconds(8);
            bool initial = false;
            while (DateTime.UtcNow < initialDeadline)
            {
                var p = port.readPacket();
                if (p.msgid != (uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT || p.sysid != 1 || p.compid != 1) continue;
                var hb = p.ToStructure<MAVLink.mavlink_heartbeat_t>();
                if (hb.custom_mode != 0 || (hb.base_mode & 128) != 0) throw new InvalidOperationException("unexpected initial heartbeat");
                initial = true; break;
            }
            if (!initial) throw new TimeoutException("initial heartbeat");
            Console.WriteLine("INITIAL_MODE=0 ARMED=False");
            var mode = new MAVLink.mavlink_set_mode_t { target_system = 1, base_mode = 1, custom_mode = 999 };
            port.setMode(1, 1, mode);
            Console.WriteLine("INVALID_MODE_CALL_RETURNED");
            var deadline = DateTime.UtcNow.AddSeconds(7);
            int observed = 0;
            while (DateTime.UtcNow < deadline)
            {
                var p = port.readPacket();
                if (p.msgid != (uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT || p.sysid != 1 || p.compid != 1) continue;
                var hb = p.ToStructure<MAVLink.mavlink_heartbeat_t>();
                Console.WriteLine("HEARTBEAT_MODE=" + hb.custom_mode + " ARMED=" + ((hb.base_mode & 128) != 0));
                if (hb.custom_mode != 0 || (hb.base_mode & 128) != 0) throw new InvalidOperationException("unexpected changed or armed heartbeat");
                observed++;
            }
            Console.WriteLine("FINAL_MODE=0 ARMED=False HEARTBEATS=" + observed);
            if (observed == 0) throw new TimeoutException("post-request heartbeat");
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
