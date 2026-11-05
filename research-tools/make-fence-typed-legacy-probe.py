from pathlib import Path
root = Path(__file__).resolve().parent.parent
source = (root / 'research-tools/FenceLegacyProbe.cs').read_text()
source = source.replace('public static class FenceLegacyProbe', 'public static class FenceTypedLegacyProbe')
start = source.index('            bool setTotal =')
end = source.index('        } catch (Exception e)', start)
replacement = '''            var points = new[] { new PointLatLngAlt(-35.363261,149.165230), new PointLatLngAlt(-35.364,149.164),
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
'''
(root / 'research-tools/FenceTypedLegacyProbe.cs').write_text(source[:start] + replacement + source[end:])
