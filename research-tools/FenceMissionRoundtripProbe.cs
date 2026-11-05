// Typed fence and normal mission roundtrip against disposable local SITL only.
using System;
using System.Globalization;
using MissionPlanner;
using MissionPlanner.Comms;
using MissionPlanner.Utilities;
public static class FenceMissionRoundtripProbe
{
    static Locationwp Item(double lat, double lon, double alt, MAVLink.MAV_CMD cmd, float p1) {
        var item = new Locationwp().Set(lat, lon, alt, (ushort)cmd); item.p1 = p1; return item;
    }
    static void Upload(MAVLinkInterface port, MAVLink.MAV_MISSION_TYPE type, Locationwp[] items) {
        port.setWPTotal((ushort)items.Length, type);
        for (ushort i = 0; i < items.Length; i++) {
            var frame = type == MAVLink.MAV_MISSION_TYPE.MISSION ? MAVLink.MAV_FRAME.GLOBAL_RELATIVE_ALT : MAVLink.MAV_FRAME.GLOBAL;
            var result = port.setWP(items[i], i, frame, use_int: true, mission_type: type);
            Console.WriteLine("UPLOAD=" + type + ":" + i + ":" + result);
            if (result != MAVLink.MAV_MISSION_RESULT.MAV_MISSION_ACCEPTED) throw new Exception("upload rejected");
        }
    }
    static Locationwp[] Read(MAVLinkInterface port, MAVLink.MAV_MISSION_TYPE type, Locationwp[] expected) {
        ushort count = port.getWPCount(type);
        Console.WriteLine("COUNT=" + type + ":" + count);
        if (count != expected.Length) throw new Exception("count mismatch " + type);
        var returned = new Locationwp[count];
        for (ushort i = 0; i < count; i++) {
            returned[i] = port.getWP(i, type);
            var v = returned[i];
            Console.WriteLine("READ=" + type + ":" + i + ":" + v.id + ":" + v.p1.ToString("R", CultureInfo.InvariantCulture) + ":" + v.lat.ToString("R", CultureInfo.InvariantCulture) + ":" + v.lng.ToString("R", CultureInfo.InvariantCulture) + ":" + v.alt.ToString("R", CultureInfo.InvariantCulture));
            bool home = type == MAVLink.MAV_MISSION_TYPE.MISSION && i == 0;
            if (v.id != expected[i].id || Math.Abs(v.p1 - expected[i].p1) > 0.01 || (!home && (Math.Abs(v.lat - expected[i].lat) > 0.0000002 || Math.Abs(v.lng - expected[i].lng) > 0.0000002)) || Math.Abs(v.alt - expected[i].alt) > 0.01)
                throw new Exception("item mismatch " + type + ":" + i);
        }
        return returned;
    }
    public static int Main(string[] args) {
        MAVLinkInterface port = null;
        try {
            log4net.Config.BasicConfigurator.Configure();
            port = new MAVLinkInterface { BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[0] } };
            port.Open(false, false, false);
            Console.WriteLine("OPEN=" + port.BaseStream.IsOpen + " SELECTED=" + port.sysidcurrent + ":" + port.compidcurrent);
            System.Threading.Thread.Sleep(8000);
            var mission = new[] { Item(-35.363261, 149.165230, 0, MAVLink.MAV_CMD.WAYPOINT, 0), Item(-35.363, 149.1655, 20, MAVLink.MAV_CMD.WAYPOINT, 0) };
            var fence = new[] { Item(-35.364, 149.164, 0, MAVLink.MAV_CMD.FENCE_POLYGON_VERTEX_INCLUSION, 3),
                                Item(-35.362, 149.164, 0, MAVLink.MAV_CMD.FENCE_POLYGON_VERTEX_INCLUSION, 3),
                                Item(-35.363, 149.167, 0, MAVLink.MAV_CMD.FENCE_POLYGON_VERTEX_INCLUSION, 3),
                                Item(-35.363, 149.1658, 0, MAVLink.MAV_CMD.FENCE_CIRCLE_EXCLUSION, 25) };
            Upload(port, MAVLink.MAV_MISSION_TYPE.MISSION, mission);
            var before = Read(port, MAVLink.MAV_MISSION_TYPE.MISSION, mission);
            Upload(port, MAVLink.MAV_MISSION_TYPE.FENCE, fence);
            Read(port, MAVLink.MAV_MISSION_TYPE.FENCE, fence);
            var after = Read(port, MAVLink.MAV_MISSION_TYPE.MISSION, mission);
            for (int i = 0; i < before.Length; i++) {
                if (before[i].id != after[i].id || before[i].p1 != after[i].p1 || before[i].lat != after[i].lat || before[i].lng != after[i].lng || before[i].alt != after[i].alt)
                    throw new Exception("mission changed after fence upload");
            }
            Console.WriteLine("MISSION_PRESERVED=True FENCE_ROUNDTRIP=True");
            System.Threading.Thread.Sleep(12000);
            Console.WriteLine("POST_UPLOAD_WAIT_SECONDS=12");
            return 0;
        } catch (Exception e) { Console.WriteLine("ERROR=" + e); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
