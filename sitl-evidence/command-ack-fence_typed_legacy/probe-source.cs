// Legacy fence-point protocol against disposable disarmed SITL only.
using System;
using System.Globalization;
using MissionPlanner;
using MissionPlanner.Comms;
using MissionPlanner.Utilities;
public static class FenceTypedLegacyProbe
{
    public static int Main(string[] args) {
        MAVLinkInterface port = null;
        try {
            log4net.Config.BasicConfigurator.Configure();
            port = new MAVLinkInterface { BaseStream = new TcpSerial { Host = "127.0.0.1", Port = args[0] } };
            port.Open(false, false, false);
            Console.WriteLine("OPEN=" + port.BaseStream.IsOpen + " SELECTED=" + port.sysidcurrent + ":" + port.compidcurrent);
            System.Threading.Thread.Sleep(8000);
            double enabled = port.GetParam("FENCE_ENABLE");
            double total = port.GetParam("FENCE_TOTAL");
            Console.WriteLine("INITIAL_ENABLE=" + enabled + " TOTAL=" + total);
            if (enabled != 0 || total != 0) throw new Exception("unexpected initial fence");
            double action = port.GetParam("FENCE_ACTION");
            Console.WriteLine("INITIAL_ACTION=" + action);
            bool disabled = port.setParam("FENCE_ACTION", 0);
            Console.WriteLine("SET_ACTION_ZERO=" + disabled + " READBACK=" + port.GetParam("FENCE_ACTION"));
            if (!disabled) throw new Exception("setting fence action failed");
            var points = new[] { new PointLatLngAlt(-35.363261,149.165230), new PointLatLngAlt(-35.364,149.164),
                                 new PointLatLngAlt(-35.362,149.164), new PointLatLngAlt(-35.363,149.167) };
            port.setWPTotal((ushort)points.Length, MAVLink.MAV_MISSION_TYPE.FENCE);
            for (ushort i=0; i<points.Length; i++) {
                ushort command = (ushort)(i == 0 ? 5000 : 5001);
                var item = new Locationwp().Set(points[i].Lat, points[i].Lng, 0, command);
                item.p1 = i == 0 ? 0 : 3;
                var result = port.setWP(item, i, MAVLink.MAV_FRAME.GLOBAL, use_int: true, mission_type: MAVLink.MAV_MISSION_TYPE.FENCE);
                Console.WriteLine("TYPED_UPLOAD=" + i + ":" + result);
                if (result != MAVLink.MAV_MISSION_RESULT.MAV_MISSION_ACCEPTED) throw new Exception("typed upload rejected");
            }
            Console.WriteLine("LEGACY_TOTAL=" + port.GetParam("FENCE_TOTAL"));
            for (int i=0; i<5; i++) {
                var response = port.getFencePoint(i).GetAwaiter().GetResult();
                Console.WriteLine("LEGACY_ITEM=" + i + ":" + response.Item2 + ":" + response.Item1.Lat.ToString("R",CultureInfo.InvariantCulture) + ":" + response.Item1.Lng.ToString("R",CultureInfo.InvariantCulture));
            }
            Console.WriteLine("REVERSE_INTEROP_READ=True"); return 0;
        } catch (Exception e) { Console.WriteLine("ERROR=" + e); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
