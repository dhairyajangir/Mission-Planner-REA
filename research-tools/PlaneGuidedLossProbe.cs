// Observe lost guided-item ACKs with a disposable, disarmed Plane SITL.
using System;
using System.Diagnostics;
using MissionPlanner;
using MissionPlanner.Comms;
using MissionPlanner.Utilities;
class PlaneGuidedLossProbe {
    static MAVLinkInterface p;
    static byte sys, comp;
    static void WaitGuided() {
        var end = DateTime.UtcNow.AddSeconds(15);
        while (DateTime.UtcNow < end) {
            var m = p.readPacket();
            if (m.sysid != sys || m.compid != comp || m.msgid != (uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT) continue;
            var h = m.ToStructure<MAVLink.mavlink_heartbeat_t>();
            Console.WriteLine("HEARTBEAT mode=" + h.custom_mode + " armed=" + ((h.base_mode & 128) != 0));
            if ((h.base_mode & 128) != 0) throw new Exception("unexpected armed simulator");
            if (h.custom_mode == 15) return;
        }
        throw new Exception("no guided heartbeat");
    }
    static int Main(string[] args) {
        try {
            log4net.Config.BasicConfigurator.Configure();
            p = new MAVLinkInterface { BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[0] } };
            p.Open(false, false, false);
            sys = (byte)p.sysidcurrent; comp = (byte)p.compidcurrent;
            Console.WriteLine("SELECTED=" + sys + ":" + comp + " FIRMWARE=" + p.MAV.cs.firmware);
            p.setMode(sys, comp, new MAVLink.mavlink_set_mode_t { target_system = sys, base_mode = 1, custom_mode = 15 });
            WaitGuided();
            var before = p.MAV.GuidedMode;
            Console.WriteLine("BEFORE x=" + before.x + " y=" + before.y + " z=" + before.z);
            var point = new Locationwp().Set(-35.3632, 149.1652, 22, (ushort)MAVLink.MAV_CMD.WAYPOINT);
            point.frame = (byte)MAVLink.MAV_FRAME.GLOBAL_RELATIVE_ALT;
            var clock = Stopwatch.StartNew();
            p.setGuidedModeWP(sys, comp, point, false);
            clock.Stop();
            var after = p.MAV.GuidedMode;
            Console.WriteLine("RETURNED elapsed_ms=" + clock.ElapsedMilliseconds);
            Console.WriteLine("AFTER x=" + after.x + " y=" + after.y + " z=" + after.z);
            WaitGuided();
            return 0;
        } catch (Exception e) { Console.WriteLine("UNHANDLED=" + e); return 1; }
        finally { if (p != null) p.Close(); }
    }
}
