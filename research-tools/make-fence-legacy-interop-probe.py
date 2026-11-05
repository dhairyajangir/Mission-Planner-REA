from pathlib import Path

root = Path(__file__).resolve().parent.parent
source = (root / 'research-tools/FenceLegacyProbe.cs').read_text()
source = source.replace('public static class FenceLegacyProbe', 'public static class FenceLegacyInteropProbe')
old = 'Console.WriteLine("LEGACY_ROUNDTRIP=True"); return 0;'
new = '''Console.WriteLine("LEGACY_ROUNDTRIP=True");
            ushort count = port.getWPCount(MAVLink.MAV_MISSION_TYPE.FENCE);
            Console.WriteLine("TYPED_COUNT=" + count);
            if (count == 0 || count > 20) throw new Exception("unexpected typed count");
            for (ushort i=0; i<count; i++) {
                var item = port.getWP(i, MAVLink.MAV_MISSION_TYPE.FENCE);
                Console.WriteLine("TYPED_ITEM=" + i + ":" + item.id + ":" + item.p1.ToString("R",CultureInfo.InvariantCulture) + ":" + item.lat.ToString("R",CultureInfo.InvariantCulture) + ":" + item.lng.ToString("R",CultureInfo.InvariantCulture));
            }
            Console.WriteLine("INTEROP_READ=True"); return 0;'''
assert source.count(old) == 1
(root / 'research-tools/FenceLegacyInteropProbe.cs').write_text(source.replace(old, new))
