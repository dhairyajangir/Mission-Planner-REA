// Legacy fence-point protocol against disposable disarmed SITL only.
using System;
using System.Globalization;
using MissionPlanner;
using MissionPlanner.Comms;
using MissionPlanner.Utilities;
public static class FenceLegacyInteropProbe
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
            bool setTotal = port.setParam("FENCE_TOTAL", 5);
            Console.WriteLine("SET_TOTAL=" + setTotal + " READBACK=" + port.GetParam("FENCE_TOTAL"));
            if (!setTotal) throw new Exception("setting fence total failed");
            System.Threading.Thread.Sleep(2000);
            var points = new[] { new PointLatLngAlt(-35.363261,149.165230), new PointLatLngAlt(-35.364,149.164),
                                 new PointLatLngAlt(-35.362,149.164), new PointLatLngAlt(-35.363,149.167),
                                 new PointLatLngAlt(-35.364,149.164) };
            for (byte i=0; i<points.Length; i++) {
                bool accepted = port.setFencePoint(i, points[i], (byte)points.Length);
                Console.WriteLine("SET_POINT=" + i + ":" + accepted);
                if (!accepted) throw new Exception("point rejected " + i);
            }
            for (int i=0; i<points.Length; i++) {
                var response = port.getFencePoint(i).GetAwaiter().GetResult();
                double distance = response.Item1.GetDistance(points[i]);
                Console.WriteLine("READ_POINT=" + i + ":" + response.Item2 + ":" + response.Item1.Lat.ToString("R",CultureInfo.InvariantCulture) + ":" + response.Item1.Lng.ToString("R",CultureInfo.InvariantCulture) + ":DIST=" + distance.ToString("R",CultureInfo.InvariantCulture));
                if (response.Item2 != points.Length || distance >= 5) throw new Exception("point mismatch " + i);
            }
            Console.WriteLine("LEGACY_ROUNDTRIP=True");
            ushort count = port.getWPCount(MAVLink.MAV_MISSION_TYPE.FENCE);
            Console.WriteLine("TYPED_COUNT=" + count);
            if (count == 0 || count > 20) throw new Exception("unexpected typed count");
            for (ushort i=0; i<count; i++) {
                var item = port.getWP(i, MAVLink.MAV_MISSION_TYPE.FENCE);
                Console.WriteLine("TYPED_ITEM=" + i + ":" + item.id + ":" + item.p1.ToString("R",CultureInfo.InvariantCulture) + ":" + item.lat.ToString("R",CultureInfo.InvariantCulture) + ":" + item.lng.ToString("R",CultureInfo.InvariantCulture));
            }
            Console.WriteLine("INTEROP_READ=True"); return 0;
        } catch (Exception e) { Console.WriteLine("ERROR=" + e); return 1; }
        finally { if (port != null) port.Close(); }
    }
}
