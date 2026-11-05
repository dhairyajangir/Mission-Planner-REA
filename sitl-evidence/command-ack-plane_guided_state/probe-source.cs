// Disposable Plane SITL: guided-item cache and ordinary mission readback.
using System;
using System.Globalization;
using System.Threading;
using MissionPlanner;
using MissionPlanner.Comms;
using MissionPlanner.Utilities;
class PlaneGuidedStateProbe {
    static MAVLinkInterface p;
    static byte sys, comp;
    static void State(string label) {
        var s = p.MAV.GuidedMode;
        Console.WriteLine(label + " x=" + s.x + " y=" + s.y + " z=" + s.z);
    }
    static void Mode(uint target) {
        var end = DateTime.UtcNow.AddSeconds(15);
        while (DateTime.UtcNow < end) {
            var m = p.readPacket();
            if (m.sysid != sys || m.compid != comp || m.msgid != (uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT) continue;
            var h = m.ToStructure<MAVLink.mavlink_heartbeat_t>();
            Console.WriteLine("HEARTBEAT mode=" + h.custom_mode + " armed=" + ((h.base_mode & 128) != 0));
            if ((h.base_mode & 128) != 0) throw new Exception("unexpected armed simulator");
            if (h.custom_mode == target) return;
        }
        throw new Exception("mode timeout");
    }
    static Locationwp Point(double lat, double lon, double alt) {
        var q = new Locationwp().Set(lat, lon, alt, (ushort)MAVLink.MAV_CMD.WAYPOINT);
        q.frame = (byte)MAVLink.MAV_FRAME.GLOBAL_RELATIVE_ALT;
        return q;
    }
    static void Mission(string label) {
        var count = p.getWPCount(); var wp = p.getWP(1);
        Console.WriteLine(string.Format(CultureInfo.InvariantCulture, "{0} count={1} lat={2:R} lon={3:R} alt={4:R}", label, count, wp.lat, wp.lng, wp.alt));
        if (count != 2 || Math.Abs(wp.lat + 35.363) > 0.0000002 || Math.Abs(wp.lng - 149.1655) > 0.0000002 || wp.alt != 20) throw new Exception("mission mismatch");
    }
    static int Main(string[] args) {
        try {
            log4net.Config.BasicConfigurator.Configure();
            p = new MAVLinkInterface { BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[0] } };
            p.Open(false, false, false); sys = (byte)p.sysidcurrent; comp = (byte)p.compidcurrent;
            Console.WriteLine("FIRMWARE=" + p.MAV.cs.firmware);
            Mode(0); Thread.Sleep(15000);
            p.setWPTotal(2);
            var a = p.setWP(Point(-35.363261,149.165230,0), 0, MAVLink.MAV_FRAME.GLOBAL_RELATIVE_ALT, use_int:true);
            var b = p.setWP(Point(-35.363,149.1655,20), 1, MAVLink.MAV_FRAME.GLOBAL_RELATIVE_ALT, use_int:true);
            Console.WriteLine("UPLOAD=" + a + "," + b);
            if (a != MAVLink.MAV_MISSION_RESULT.MAV_MISSION_ACCEPTED || b != MAVLink.MAV_MISSION_RESULT.MAV_MISSION_ACCEPTED) throw new Exception("upload failed");
            Mission("MISSION_BEFORE"); State("CACHE_BEFORE");
            p.setGuidedModeWP(sys, comp, Point(-35.3631,149.1651,21), false);
            Console.WriteLine("MANUAL_RETURNED"); State("CACHE_AFTER_REJECTION"); Mission("MISSION_AFTER_REJECTION");
            p.setMode(sys, comp, new MAVLink.mavlink_set_mode_t { target_system = sys, base_mode = 1, custom_mode = 15 }); Mode(15);
            p.setGuidedModeWP(sys, comp, Point(-35.3632,149.1652,22), false);
            Console.WriteLine("GUIDED_RETURNED"); State("CACHE_AFTER_ACCEPTANCE"); Mission("MISSION_AFTER_ACCEPTANCE");
            Mode(15); return 0;
        } catch (Exception e) { Console.WriteLine("UNHANDLED=" + e); return 1; }
        finally { if (p != null) p.Close(); }
    }
}
