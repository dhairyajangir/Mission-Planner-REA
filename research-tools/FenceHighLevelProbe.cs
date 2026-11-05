// Planner's high-level mav_mission path against disposable local SITL.
using System;
using System.Collections.Generic;
using System.Globalization;
using MissionPlanner;
using MissionPlanner.ArduPilot;
using MissionPlanner.Comms;
using MissionPlanner.Utilities;
public static class FenceHighLevelProbe
{
    static Locationwp Item(double lat, double lon, double alt, MAVLink.MAV_CMD cmd, float p1, MAVLink.MAV_FRAME frame) {
        var value = new Locationwp().Set(lat, lon, alt, (ushort)cmd); value.p1 = p1; value.frame = (byte)frame; return value;
    }
    static void Upload(MAVLinkInterface port, MAVLink.MAV_MISSION_TYPE type, List<Locationwp> items) {
        mav_mission.upload(port, 1, 1, type, items).GetAwaiter().GetResult();
        Console.WriteLine("UPLOAD_COMPLETE=" + type);
    }
    static List<Locationwp> Download(MAVLinkInterface port, MAVLink.MAV_MISSION_TYPE type) {
        var items = mav_mission.download(port, 1, 1, type).GetAwaiter().GetResult();
        Console.WriteLine("COUNT=" + type + ":" + items.Count);
        for (int i = 0; i < items.Count; i++) {
            var v = items[i];
            Console.WriteLine("READ=" + type + ":" + i + ":" + v.id + ":" + v.p1.ToString("R", CultureInfo.InvariantCulture) + ":" + v.lat.ToString("R", CultureInfo.InvariantCulture) + ":" + v.lng.ToString("R", CultureInfo.InvariantCulture) + ":" + v.alt.ToString("R", CultureInfo.InvariantCulture));
        }
        return items;
    }
    static void Check(List<Locationwp> actual, List<Locationwp> expected, bool homePlaceholder) {
        if (actual.Count != expected.Count) throw new Exception("count mismatch");
        for (int i = 0; i < actual.Count; i++) {
            var a = actual[i]; var e = expected[i];
            if (a.id != e.id || Math.Abs(a.p1 - e.p1) > 0.01 || Math.Abs(a.alt - e.alt) > 0.01 ||
                (!(homePlaceholder && i == 0) && (Math.Abs(a.lat - e.lat) > 0.0000002 || Math.Abs(a.lng - e.lng) > 0.0000002)))
                throw new Exception("item mismatch " + i);
        }
    }
    public static int Main(string[] args) {
        MAVLinkInterface port = null;
        try {
            log4net.Config.BasicConfigurator.Configure();
            port = new MAVLinkInterface { BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[0] } };
            port.Open(false, false, false);
            Console.WriteLine("OPEN=" + port.BaseStream.IsOpen + " SELECTED=" + port.sysidcurrent + ":" + port.compidcurrent);
            var until = DateTime.UtcNow.AddSeconds(15);
            uint required = (uint)MAVLink.MAV_PROTOCOL_CAPABILITY.MISSION_INT | (uint)MAVLink.MAV_PROTOCOL_CAPABILITY.MISSION_FENCE;
            while (DateTime.UtcNow < until && (port.MAVlist[1,1].cs.capabilities & required) != required) port.readPacket();
            Console.WriteLine("CAPABILITIES=" + port.MAVlist[1,1].cs.capabilities + " REQUIRED=" + required);
            if ((port.MAVlist[1,1].cs.capabilities & required) != required) throw new Exception("required capabilities unavailable");
            var mission = new List<Locationwp> { Item(-35.363261, 149.165230, 0, MAVLink.MAV_CMD.WAYPOINT, 0, MAVLink.MAV_FRAME.GLOBAL_RELATIVE_ALT),
                                                 Item(-35.363, 149.1655, 20, MAVLink.MAV_CMD.WAYPOINT, 0, MAVLink.MAV_FRAME.GLOBAL_RELATIVE_ALT) };
            var fence = new List<Locationwp> { Item(-35.364, 149.164, 0, MAVLink.MAV_CMD.FENCE_POLYGON_VERTEX_INCLUSION, 3, MAVLink.MAV_FRAME.GLOBAL),
                                               Item(-35.362, 149.164, 0, MAVLink.MAV_CMD.FENCE_POLYGON_VERTEX_INCLUSION, 3, MAVLink.MAV_FRAME.GLOBAL),
                                               Item(-35.363, 149.167, 0, MAVLink.MAV_CMD.FENCE_POLYGON_VERTEX_INCLUSION, 3, MAVLink.MAV_FRAME.GLOBAL),
                                               Item(-35.363, 149.1658, 0, MAVLink.MAV_CMD.FENCE_CIRCLE_EXCLUSION, 25, MAVLink.MAV_FRAME.GLOBAL) };
            Upload(port, MAVLink.MAV_MISSION_TYPE.MISSION, mission);
            var before = Download(port, MAVLink.MAV_MISSION_TYPE.MISSION); Check(before, mission, true);
            Upload(port, MAVLink.MAV_MISSION_TYPE.FENCE, fence);
            var fenceRead = Download(port, MAVLink.MAV_MISSION_TYPE.FENCE); Check(fenceRead, fence, false);
            var after = Download(port, MAVLink.MAV_MISSION_TYPE.MISSION); Check(after, mission, true);
            Check(after, before, false);
            Console.WriteLine("HIGHLEVEL_FENCE_ROUNDTRIP=True MISSION_PRESERVED=True");
            return 0;
        } catch (Exception e) { Console.WriteLine("ERROR=" + e); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
