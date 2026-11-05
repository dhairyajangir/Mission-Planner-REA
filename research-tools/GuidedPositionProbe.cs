// Tests original Mission Planner assembly against a disposable disarmed SITL.
using System;
using System.Threading;
using MissionPlanner;
using MissionPlanner.Comms;
using MissionPlanner.Utilities;
public static class GuidedPositionProbe {
    static MAVLink.mavlink_heartbeat_t WaitMode(MAVLinkInterface p, uint mode) {
        var until = DateTime.UtcNow.AddSeconds(12);
        while (DateTime.UtcNow < until) {
            var m = p.readPacket();
            if (m.msgid != (uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT || m.sysid != 1 || m.compid != 1) continue;
            var hb = m.ToStructure<MAVLink.mavlink_heartbeat_t>();
            Console.WriteLine("HEARTBEAT_MODE=" + hb.custom_mode + " ARMED=" + ((hb.base_mode & 128) != 0));
            if ((hb.base_mode & 128) != 0) throw new Exception("SITL unexpectedly armed");
            if (hb.custom_mode == mode) return hb;
        }
        throw new Exception("Mode heartbeat timeout");
    }
    static Locationwp Point(double lat, double lon, double alt) {
        return new Locationwp().Set(lat, lon, alt, (ushort)MAVLink.MAV_CMD.WAYPOINT);
    }
    public static int Main(string[] args) {
        MAVLinkInterface p = null;
        try {
            log4net.Config.BasicConfigurator.Configure();
            p = new MAVLinkInterface { BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[0] } };
            p.Open(false, false, false);
            WaitMode(p, 0);
            p.setGuidedModeWP(1, 1, Point(0, 149.165, 10), false);
            p.setGuidedModeWP(1, 1, Point(-35.363, 0, 10), false);
            p.setGuidedModeWP(1, 1, Point(-35.363, 149.165, 0), false);
            Console.WriteLine("ZERO_CASES_RETURNED");
            p.setGuidedModeWP(1, 1, Point(-35.3631, 149.1651, 11), false);
            Console.WriteLine("STABILIZE_TARGET_SENT");
            Thread.Sleep(500);
            p.setMode(1, 1, new MAVLink.mavlink_set_mode_t { target_system = 1, base_mode = 1, custom_mode = 4 });
            WaitMode(p, 4);
            p.setGuidedModeWP(1, 1, Point(-35.3632, 149.1652, 12), false);
            Console.WriteLine("GUIDED_TARGET_SENT");
            Thread.Sleep(1500);
            WaitMode(p, 4);
            return 0;
        } catch (Exception e) { Console.WriteLine("ERROR=" + e); return 1; }
        finally { if (p != null) p.Close(); }
    }
}
