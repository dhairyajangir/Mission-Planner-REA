"""Verify typed upload and legacy readback from captured MAVLink frames."""
import hashlib
import json
import math
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
out = root / 'sitl-evidence/command-ack-fence_typed_legacy'
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
relay = json.loads((out / 'relay-result.json').read_text())
assert relay['case'] == 'fence_typed_legacy' and not relay['errors'] and relay['closed_by'] == 'client'
assert relay['buffered_bytes_at_close'] == 0 and relay['binary_sha256'] == sha(root / 'sitl-evidence/arducopter')
assert all(sha(out / name) == digest for name,digest in relay['capture_sha256'].items())
def decode(path):
    parser = ardupilotmega.MAVLink(None); parser.robust_parsing = True
    found, bad = [], 0
    for byte in path.read_bytes():
        msg = parser.parse_char(bytes([byte]))
        if msg is None: continue
        if msg.get_type() == 'BAD_DATA': bad += 1; continue
        record = msg.to_dict(); record['source'] = [msg.get_srcSystem(), msg.get_srcComponent()]; found.append(record)
    return found, bad
up, bad_up = decode(out / 'to_sitl_output.bin'); down, bad_down = decode(out / 'to_client_output.bin')
pick = lambda records, kind: [m for m in records if m['mavpackettype'] == kind]
items = [m for m in pick(up, 'MISSION_ITEM_INT') if m['mission_type'] == 1]
fetches, points = pick(up, 'FENCE_FETCH_POINT'), pick(down, 'FENCE_POINT')
heartbeats = [m for m in pick(down, 'HEARTBEAT') if m['source'] == [1,1]]
assert [m['seq'] for m in items] == list(range(4))
assert [m['command'] for m in items] == [5000,5001,5001,5001]
assert [m['param1'] for m in items] == [0,3,3,3]
assert [m['idx'] for m in fetches] == list(range(5)) == [m['idx'] for m in points]
expected = [(-35.363261,149.165230),(-35.364,149.164),(-35.362,149.164),(-35.363,149.167),(-35.364,149.164)]
def distance(a,b,c,d):
    v=math.sin(math.radians(c-a)/2)**2+math.cos(math.radians(a))*math.cos(math.radians(c))*math.sin(math.radians(d-b)/2)**2
    return 2*6371000*math.asin(math.sqrt(v))
assert all(distance(m['x']/1e7,m['y']/1e7,*expected[i]) < 5 for i,m in enumerate(items))
assert all(m['count'] == 5 and distance(m['lat'],m['lng'],*expected[i]) < 5 for i,m in enumerate(points))
assert heartbeats and all(not (m['base_mode'] & 128) for m in heartbeats)
assert (out / 'probe-exit.txt').read_text().strip() == '0'
log = (out / 'probe.log').read_text(encoding='utf8',errors='replace')
assert all(s in log for s in ['LEGACY_TOTAL=5','REVERSE_INTEROP_READ=True'])
summary = {'scope':'One disarmed Copter 4.7.2 SITL run; typed upload then legacy fence read',
           'relay':relay,'typed_items':items,'fetches':fetches,'points':points,'heartbeats':heartbeats,
           'bad_data_fragments':{'uplink':bad_up,'downlink':bad_down},
           'hashes':{name:sha(out/name) for name in ['probe-source.cs','probe.exe','probe.log','probe-exit.txt']},
           'library_hashes':{name:sha(root/'mission-planner-portable'/name) for name in
                ['MissionPlanner.ArduPilot.dll','MissionPlanner.Utilities.dll','MissionPlanner.Comms.dll','MAVLink.dll','Interfaces.dll','System.ValueTuple.dll','FenceTypedLegacyProbe.exe.config']}}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print('Typed items:',len(items),'legacy points:',len(points))
