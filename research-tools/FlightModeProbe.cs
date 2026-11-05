// Original Mission Planner library setting mode in a disposable disarmed Copter SITL.
using System;
using MissionPlanner;
using MissionPlanner.Comms;
public static class FlightModeProbe
{
    static MAVLink.mavlink_heartbeat_t? WaitHeartbeat(MAVLinkInterface port, DateTime deadline, uint? target)
    {
        MAVLink.mavlink_heartbeat_t? last = null;
        while (DateTime.UtcNow < deadline)
        {
            var packet = port.readPacket();
            if (packet.msgid != (uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT || packet.sysid != 1 || packet.compid != 1) continue;
            var hb = packet.ToStructure<MAVLink.mavlink_heartbeat_t>();
            last = hb;
            Console.WriteLine("HEARTBEAT_MODE=" + hb.custom_mode + " ARMED=" + ((hb.base_mode & 128) != 0));
            if (target.HasValue && hb.custom_mode == target.Value) break;
        }
        return last;
    }
    public static int Main(string[] args)
    {
        MAVLinkInterface port = null;
        try
        {
            log4net.Config.BasicConfigurator.Configure();
            port = new MAVLinkInterface { BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[0] } };
            port.Open(false, false, false);
            Console.WriteLine("OPEN=" + port.BaseStream.IsOpen + " SELECTED=" + port.sysidcurrent + ":" + port.compidcurrent);
            var initial = WaitHeartbeat(port, DateTime.UtcNow.AddSeconds(8), 0);
            if (!initial.HasValue || initial.Value.custom_mode != 0 || (initial.Value.base_mode & 128) != 0)
                throw new InvalidOperationException("expected disarmed STABILIZE heartbeat");
            Console.WriteLine("INITIAL_MODE=" + initial.Value.custom_mode + " ARMED=False");
            var mode = new MAVLink.mavlink_set_mode_t { target_system = 1, base_mode = 1, custom_mode = 4 };
            port.setMode(1, 1, mode);
            Console.WriteLine("SET_MODE_RETURNED");
            bool expectChange = args[1] != "drop_all";
            var after = WaitHeartbeat(port, DateTime.UtcNow.AddSeconds(7), expectChange ? (uint?)4 : null);
            if (!after.HasValue || (after.Value.base_mode & 128) != 0) throw new InvalidOperationException("missing or armed heartbeat");
            Console.WriteLine("FINAL_MODE=" + after.Value.custom_mode + " ARMED=False");
            if (after.Value.custom_mode != (expectChange ? 4U : 0U)) throw new InvalidOperationException("unexpected mode");
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
