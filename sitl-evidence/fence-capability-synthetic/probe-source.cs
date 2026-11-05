// In-memory transport, no simulator or network. Exercises high-level guard branches.
using System;
using System.Collections.Generic;
using MissionPlanner;
using MissionPlanner.ArduPilot;
using MissionPlanner.Utilities;
public static class FenceCapabilityProbe
{
    static void Expect(string name, string expected, Action action, ModeCaptureSerial serial) {
        long before = serial.output.Length;
        try { action(); throw new Exception("guard did not reject " + name); }
        catch (Exception ex) {
            if (ex.Message != expected) throw;
            Console.WriteLine(name + "=" + ex.Message + " BYTES=" + (serial.output.Length - before));
            if (serial.output.Length != before) throw new Exception("guard sent bytes");
        }
    }
    public static int Main(string[] args) {
        try {
            var serial = new ModeCaptureSerial();
            var port = new MAVLinkInterface { BaseStream = serial };
            port.sysidcurrent = 1; port.compidcurrent = 1;
            port.MAVlist[1,1].cs.capabilities = 0;
            port.MAVlist[1,1].mavlinkv2 = false;
            string noFence = "Fence mission items not supported, please use legacy geofence";
            string noV2 = "Mission type only supported under mavlink2";
            Expect("FENCE_UPLOAD", noFence, () => mav_mission.upload(port, 1, 1, MAVLink.MAV_MISSION_TYPE.FENCE, new List<Locationwp>()).GetAwaiter().GetResult(), serial);
            Expect("FENCE_DOWNLOAD", noFence, () => mav_mission.download(port, 1, 1, MAVLink.MAV_MISSION_TYPE.FENCE).GetAwaiter().GetResult(), serial);
            Expect("RALLY_UPLOAD", noV2, () => mav_mission.upload(port, 1, 1, MAVLink.MAV_MISSION_TYPE.RALLY, new List<Locationwp>()).GetAwaiter().GetResult(), serial);
            Expect("RALLY_DOWNLOAD", noV2, () => mav_mission.download(port, 1, 1, MAVLink.MAV_MISSION_TYPE.RALLY).GetAwaiter().GetResult(), serial);
            System.IO.File.WriteAllBytes(args[0], serial.output.ToArray());
            serial.Dispose(); return 0;
        } catch (Exception e) { Console.WriteLine("ERROR=" + e); return 1; }
    }
}
