// Dedicated loopback-only disposable source-built Copter SITL experiment.
using System;
using System.Globalization;
using MissionPlanner;
using MissionPlanner.Comms;
using MissionPlanner.Utilities;
class GuidedFlightProbe {
    static MAVLinkInterface port;
    static uint mode;
    static bool armed;
    static double lat, lon, altitude;
    static void Pump(double seconds, Func<bool> done) {
        DateTime end = DateTime.UtcNow.AddSeconds(seconds);
        while (DateTime.UtcNow < end && (done == null || !done())) {
            var packet = port.readPacket();
            if (packet.sysid != 1 || packet.compid != 1) continue;
            if (packet.msgid == (uint)MAVLink.MAVLINK_MSG_ID.HEARTBEAT) {
                var h = packet.ToStructure<MAVLink.mavlink_heartbeat_t>();
                mode = h.custom_mode; armed = (h.base_mode & 128) != 0;
                Console.WriteLine("HB mode=" + mode + " armed=" + armed);
            }
            if (packet.msgid == (uint)MAVLink.MAVLINK_MSG_ID.GLOBAL_POSITION_INT) {
                var p = packet.ToStructure<MAVLink.mavlink_global_position_int_t>();
                lat = p.lat / 1e7; lon = p.lon / 1e7; altitude = p.relative_alt / 1000.0;
                Console.WriteLine(string.Format(CultureInfo.InvariantCulture, "POS {0:F7} {1:F7} {2:F3}", lat, lon, altitude));
            }
        }
    }
    static void SetMode(uint target) {
        port.setMode(1, 1, new MAVLink.mavlink_set_mode_t { target_system = 1, base_mode = 1, custom_mode = target });
        Pump(10, () => mode == target);
        if (mode != target) throw new Exception("mode not observed: " + target);
    }
    static int Main(string[] args) {
        try {
            log4net.Config.BasicConfigurator.Configure();
            port = new MAVLinkInterface { BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[0] } };
            port.Open(false, false, false);
            port.requestDatastream(MAVLink.MAV_DATA_STREAM.ALL, 4, 1, 1);
            Pump(55, null); // estimator/GPS initialization in the disposable simulator
            if (armed || lat == 0 || lon == 0) throw new Exception("bad initial state");
            SetMode(4);
            bool armAccepted = false;
            for (int attempt = 1; attempt <= 4 && !armed; attempt++) {
                armAccepted = port.doARM(1, 1, true, false);
                Console.WriteLine("ARM_ATTEMPT=" + attempt + " ACCEPTED=" + armAccepted);
                Pump(8, () => armed);
            }
            if (!armAccepted || !armed) throw new Exception("normal arm failed");
            bool takeoff = port.doCommand(1, 1, MAVLink.MAV_CMD.TAKEOFF, 0, 0, 0, 0, 0, 0, 5, true);
            Console.WriteLine("TAKEOFF_ACCEPTED=" + takeoff);
            if (!takeoff) throw new Exception("takeoff rejected");
            Pump(35, () => altitude >= 3.5);
            if (altitude < 3.5) throw new Exception("takeoff height not reached");
            double targetLat = lat + 0.00008, targetLon = lon;
            Console.WriteLine(string.Format(CultureInfo.InvariantCulture, "TARGET {0:F7} {1:F7} 5", targetLat, targetLon));
            port.setGuidedModeWP(1, 1, new Locationwp().Set(targetLat, targetLon, 5, (ushort)MAVLink.MAV_CMD.WAYPOINT), false);
            Pump(45, () => Math.Abs(lat - targetLat) < 0.000015 && Math.Abs(lon - targetLon) < 0.00002);
            double error = Math.Abs(lat - targetLat);
            Console.WriteLine(string.Format(CultureInfo.InvariantCulture, "TARGET_LAT_ERROR {0:F7}", error));
            if (error >= 0.000015 || Math.Abs(lon - targetLon) >= 0.00002) throw new Exception("target not reached in observation window");
            SetMode(9);
            Pump(50, () => !armed);
            if (armed) throw new Exception("landing did not disarm");
            Console.WriteLine("FLIGHT_SUCCESS disarmed=True");
            return 0;
        } catch (Exception ex) { Console.WriteLine("ERROR=" + ex); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
