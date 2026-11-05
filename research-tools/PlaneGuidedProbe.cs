// Original library against a disposable local source-built Plane SITL.
using System;
using MissionPlanner;
using MissionPlanner.Comms;
using MissionPlanner.Utilities;
class PlaneGuidedProbe {
    static MAVLinkInterface port;
    static byte system, component;
    static void WaitMode(uint mode) {
        DateTime until = DateTime.UtcNow.AddSeconds(15);
        while (DateTime.UtcNow < until) {
            var p = port.readPacket();
            if (p.sysid != system || p.compid != component || p.msgid != (uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT) continue;
            var h = p.ToStructure<MAVLink.mavlink_heartbeat_t>();
            Console.WriteLine("HEARTBEAT mode=" + h.custom_mode + " armed=" + ((h.base_mode & 128) != 0));
            if ((h.base_mode & 128) != 0) throw new Exception("unexpected armed simulator");
            if (h.custom_mode == mode) return;
        }
        throw new Exception("missing expected heartbeat mode " + mode);
    }
    static Locationwp Point(double lat, double lon, double alt) {
        var p = new Locationwp().Set(lat, lon, alt, (ushort)MAVLink.MAV_CMD.WAYPOINT);
        p.frame = (byte)MAVLink.MAV_FRAME.GLOBAL_RELATIVE_ALT;
        return p;
    }
    static int Main(string[] args) {
        try {
            log4net.Config.BasicConfigurator.Configure();
            port = new MAVLinkInterface { BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[0] } };
            port.Open(false, false, false);
            system = (byte)port.sysidcurrent; component = (byte)port.compidcurrent;
            Console.WriteLine("SELECTED=" + system + ":" + component + " FIRMWARE=" + port.MAV.cs.firmware);
            WaitMode(0);
            port.setGuidedModeWP(system, component, Point(0, 149.165, 20), false);
            port.setGuidedModeWP(system, component, Point(-35.363, 0, 20), false);
            port.setGuidedModeWP(system, component, Point(-35.363, 149.165, 0), false);
            Console.WriteLine("ZERO_INPUTS_RETURNED");
            port.setGuidedModeWP(system, component, Point(-35.3631, 149.1651, 21), false);
            Console.WriteLine("MANUAL_TARGET_RETURNED");
            port.setMode(system, component, new MAVLink.mavlink_set_mode_t { target_system = system, base_mode = 1, custom_mode = 15 });
            WaitMode(15);
            port.setGuidedModeWP(system, component, Point(-35.3632, 149.1652, 22), false);
            Console.WriteLine("GUIDED_TARGET_RETURNED");
            WaitMode(15);
            return 0;
        } catch (Exception e) { Console.WriteLine("ERROR=" + e); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
