from pathlib import Path
root = Path(__file__).resolve().parent.parent
s = (root/'research-tools/FenceMavftpProbe.cs').read_text()
s = s.replace('FenceMavftpProbe','FenceMavftpDropProbe')
anchor = '            var items = new List<MAVLink.mavlink_mission_item_int_t>();'
insert = '''            var baseline = new[] { Item(-35.365,149.163,MAVLink.MAV_CMD.FENCE_POLYGON_VERTEX_INCLUSION,3),
                Item(-35.361,149.163,MAVLink.MAV_CMD.FENCE_POLYGON_VERTEX_INCLUSION,3),
                Item(-35.363,149.168,MAVLink.MAV_CMD.FENCE_POLYGON_VERTEX_INCLUSION,3),
                Item(-35.363,149.165,MAVLink.MAV_CMD.FENCE_CIRCLE_EXCLUSION,15) };
            port.setWPTotal((ushort)baseline.Length, MAVLink.MAV_MISSION_TYPE.FENCE);
            for (ushort i=0; i<baseline.Length; i++) {
                var result = port.setWP(baseline[i],i,MAVLink.MAV_FRAME.GLOBAL,use_int:true,mission_type:MAVLink.MAV_MISSION_TYPE.FENCE);
                Console.WriteLine("BASELINE_UPLOAD="+i+":"+result);
                if (result != MAVLink.MAV_MISSION_RESULT.MAV_MISSION_ACCEPTED) throw new Exception("baseline failed");
            }
'''
assert s.count(anchor)==1
s=s.replace(anchor,insert+anchor)
start=s.index('            var stream = Pump(')
end=s.index('        } catch (Exception e)',start)
s=s[:start]+'''            Console.WriteLine("DROP_PROBE_COMPLETE=True"); return 0;
'''+s[end:]
(root/'research-tools/FenceMavftpDropProbe.cs').write_text(s)
