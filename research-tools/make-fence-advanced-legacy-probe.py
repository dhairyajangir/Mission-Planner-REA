from pathlib import Path
root = Path(__file__).resolve().parent.parent
source = (root / 'research-tools/FenceTypedLegacyProbe.cs').read_text()
source = source.replace('FenceTypedLegacyProbe', 'FenceAdvancedLegacyProbe')
source = source.replace('new PointLatLngAlt(-35.362,149.164), new PointLatLngAlt(-35.363,149.167) };',
                        'new PointLatLngAlt(-35.362,149.164), new PointLatLngAlt(-35.363,149.167), new PointLatLngAlt(-35.363,149.1658) };')
source = source.replace('ushort command = (ushort)(i == 0 ? 5000 : 5001);',
                        'ushort command = i == 4 ? (ushort)MAVLink.MAV_CMD.FENCE_CIRCLE_EXCLUSION : (ushort)(i == 0 ? 5000 : 5001);')
source = source.replace('item.p1 = i == 0 ? 0 : 3;', 'item.p1 = i == 0 ? 0 : i == 4 ? 25 : 3;')
start = source.index('            Console.WriteLine("LEGACY_TOTAL=')
end = source.index('        } catch (Exception e)', start)
replacement = '''            Console.WriteLine("LEGACY_TOTAL=" + port.GetParam("FENCE_TOTAL"));
            try {
                var response = port.getFencePoint(0).GetAwaiter().GetResult();
                Console.WriteLine("LEGACY_RESPONSE=" + response.Item2 + ":" + response.Item1.Lat + ":" + response.Item1.Lng);
            } catch (Exception e) { Console.WriteLine("LEGACY_ERROR=" + e.GetType().FullName + ":" + e.Message); }
            ushort count = port.getWPCount(MAVLink.MAV_MISSION_TYPE.FENCE);
            Console.WriteLine("TYPED_COUNT=" + count);
            for (ushort i=0; i<count; i++) {
                var item = port.getWP(i, MAVLink.MAV_MISSION_TYPE.FENCE);
                Console.WriteLine("TYPED_ITEM=" + i + ":" + item.id + ":" + item.p1.ToString("R",CultureInfo.InvariantCulture) + ":" + item.lat.ToString("R",CultureInfo.InvariantCulture) + ":" + item.lng.ToString("R",CultureInfo.InvariantCulture));
            }
            Console.WriteLine("ADVANCED_PROBE_COMPLETE=True"); return 0;
'''
(root / 'research-tools/FenceAdvancedLegacyProbe.cs').write_text(source[:start] + replacement + source[end:])
