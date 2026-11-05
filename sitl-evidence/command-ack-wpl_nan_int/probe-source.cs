// Disposable Copter SITL only; tests import and transfer of a synthetic NaN fixture.
using System;
using System.Globalization;
using System.Threading;
using MissionPlanner;
using MissionPlanner.Comms;
using MissionPlanner.Utilities;
class WaypointNanUploadProbe {
    static void Readback(MAVLinkInterface p, string label) {
        ushort count = p.getWPCount();
        Console.WriteLine(label + "_COUNT=" + count);
        if (count > 1) {
            var q = p.getWP(1);
            Console.WriteLine(string.Format(CultureInfo.InvariantCulture, "{0}_ITEM1={1:R},{2:R},{3:R}", label, q.lat, q.lng, q.alt));
        }
    }
    static int Main(string[] args) {
        MAVLinkInterface p = null;
        try {
            log4net.Config.BasicConfigurator.Configure();
            bool useInt = args[2] == "int";
            var fixture = WaypointFile.ReadWaypointFile(args[1]);
            Console.WriteLine("FIXTURE_COUNT=" + fixture.Count + " LAT_IS_NAN=" + double.IsNaN(fixture[1].lat));
            if (fixture.Count != 2 || !double.IsNaN(fixture[1].lat)) throw new Exception("unexpected fixture");
            p = new MAVLinkInterface { BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[0] } };
            p.Open(false, false, false);
            Thread.Sleep(15000);
            var home = new Locationwp().Set(-35.363261, 149.165230, 0, (ushort)MAVLink.MAV_CMD.WAYPOINT);
            var point = new Locationwp().Set(-35.363, 149.1655, 20, (ushort)MAVLink.MAV_CMD.WAYPOINT);
            p.setWPTotal(2);
            var a = p.setWP(home, 0, MAVLink.MAV_FRAME.GLOBAL_RELATIVE_ALT, use_int:true);
            var b = p.setWP(point, 1, MAVLink.MAV_FRAME.GLOBAL_RELATIVE_ALT, use_int:true);
            Console.WriteLine("BASELINE_RESULTS=" + a + "," + b);
            if (a != MAVLink.MAV_MISSION_RESULT.MAV_MISSION_ACCEPTED || b != MAVLink.MAV_MISSION_RESULT.MAV_MISSION_ACCEPTED) throw new Exception("baseline upload failed");
            Readback(p, "BASELINE");
            p.setWPTotal(2);
            var first = p.setWP(home, 0, MAVLink.MAV_FRAME.GLOBAL_RELATIVE_ALT, use_int:useInt);
            Console.WriteLine("REPLACE_FIRST=" + first);
            try {
                var second = p.setWP(fixture[1], 1, MAVLink.MAV_FRAME.GLOBAL_RELATIVE_ALT, use_int:useInt);
                Console.WriteLine("NAN_RESULT=" + second);
            } catch (Exception e) { Console.WriteLine("NAN_EXCEPTION=" + e.GetType().FullName + ":" + e.Message); }
            Readback(p, "AFTER");
            return 0;
        } catch (Exception e) { Console.WriteLine("UNHANDLED=" + e); return 1; }
        finally { if (p != null) p.Close(); }
    }
}
