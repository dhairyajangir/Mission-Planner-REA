// Original Mission Planner packer and MAVFTP library against disposable disarmed SITL.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using MissionPlanner;
using MissionPlanner.ArduPilot;
using MissionPlanner.ArduPilot.Mavlink;
using MissionPlanner.Comms;
using MissionPlanner.Utilities;
public static class FenceMavftpDropProbe {
    static T Pump<T>(MAVLinkInterface port, Func<T> operation) {
        var task = System.Threading.Tasks.Task.Run(operation);
        while (!task.IsCompleted) {
            if (port.BaseStream.BytesToRead > 0) port.readPacket();
            else System.Threading.Thread.Sleep(5);
        }
        return task.GetAwaiter().GetResult();
    }
    static Locationwp Item(double lat, double lon, MAVLink.MAV_CMD cmd, float p1) {
        var value = new Locationwp().Set(lat, lon, 0, (ushort)cmd); value.p1 = p1;
        value.frame = (byte)MAVLink.MAV_FRAME.GLOBAL; return value;
    }
    public static int Main(string[] args) {
        MAVLinkInterface port = null;
        try {
            log4net.Config.BasicConfigurator.Configure();
            port = new MAVLinkInterface { BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[0] } };
            port.Open(false, false, false);
            Console.WriteLine("OPEN=" + port.BaseStream.IsOpen + " SELECTED=" + port.sysidcurrent + ":" + port.compidcurrent);
            System.Threading.Thread.Sleep(8000);
            var points = new[] { Item(-35.364,149.164,MAVLink.MAV_CMD.FENCE_POLYGON_VERTEX_INCLUSION,3),
                Item(-35.362,149.164,MAVLink.MAV_CMD.FENCE_POLYGON_VERTEX_INCLUSION,3),
                Item(-35.363,149.167,MAVLink.MAV_CMD.FENCE_POLYGON_VERTEX_INCLUSION,3),
                Item(-35.363,149.1658,MAVLink.MAV_CMD.FENCE_CIRCLE_EXCLUSION,25) };
            var baseline = new[] { Item(-35.365,149.163,MAVLink.MAV_CMD.FENCE_POLYGON_VERTEX_INCLUSION,3),
                Item(-35.361,149.163,MAVLink.MAV_CMD.FENCE_POLYGON_VERTEX_INCLUSION,3),
                Item(-35.363,149.168,MAVLink.MAV_CMD.FENCE_POLYGON_VERTEX_INCLUSION,3),
                Item(-35.363,149.165,MAVLink.MAV_CMD.FENCE_CIRCLE_EXCLUSION,15) };
            port.setWPTotal((ushort)baseline.Length, MAVLink.MAV_MISSION_TYPE.FENCE);
            for (ushort i=0; i<baseline.Length; i++) {
                var result = port.setWP(baseline[i],i,MAVLink.MAV_FRAME.GLOBAL,use_int:true,mission_type:MAVLink.MAV_MISSION_TYPE.FENCE);
                Console.WriteLine("BASELINE_UPLOAD="+i+":"+result);
                if (result != MAVLink.MAV_MISSION_RESULT.MAV_MISSION_ACCEPTED) throw new Exception("baseline failed");
            }
            var items = new List<MAVLink.mavlink_mission_item_int_t>();
            foreach (var point in points) items.Add((MAVLink.mavlink_mission_item_int_t)point);
            byte[] packed = missionpck.pack(items, MAVLink.MAV_MISSION_TYPE.FENCE, 0);
            File.WriteAllBytes(Path.Combine(args[1], "upload.dat"), packed);
            var ftp = new MAVFtp(port, (byte)port.sysidcurrent, (byte)port.compidcurrent);
            Pump(port, () => { ftp.UploadFile("@MISSION/fence.dat", new MemoryStream(packed), null); return true; });
            Console.WriteLine("FTP_UPLOAD_RETURNED=True BYTES=" + packed.Length);
            ushort count = port.getWPCount(MAVLink.MAV_MISSION_TYPE.FENCE);
            Console.WriteLine("MISSION_COUNT=" + count);
            for (ushort i=0; i<count; i++) {
                var value = port.getWP(i, MAVLink.MAV_MISSION_TYPE.FENCE);
                Console.WriteLine("MISSION_ITEM=" + i + ":" + value.id + ":" + value.p1.ToString("R",CultureInfo.InvariantCulture) + ":" + value.lat.ToString("R",CultureInfo.InvariantCulture) + ":" + value.lng.ToString("R",CultureInfo.InvariantCulture));
            }
            Console.WriteLine("DROP_PROBE_COMPLETE=True"); return 0;
        } catch (Exception e) { Console.WriteLine("ERROR=" + e); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
