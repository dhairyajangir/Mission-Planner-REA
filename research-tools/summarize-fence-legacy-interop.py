"""Decode legacy writes followed by typed fence reads in disposable Copter SITL."""
import hashlib
import json
import math
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parent.parent
out = root / 'sitl-evidence/command-ack-fence_legacy_interop'
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega

sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
relay = json.loads((out / 'relay-result.json').read_text())
assert relay['case'] == 'fence_legacy_interop' and not relay['errors'] and relay['closed_by'] == 'client'
assert relay['buffered_bytes_at_close'] == 0
assert relay['binary_sha256'] == sha(root / 'sitl-evidence/arducopter')
for name, digest in relay['capture_sha256'].items():
    assert sha(out / name) == digest
def decode(path):
    parser = ardupilotmega.MAVLink(None)
    parser.robust_parsing = True
    messages, bad = [], 0
    for byte in path.read_bytes():
        msg = parser.parse_char(bytes([byte]))
        if msg is None: continue
        if msg.get_type() == 'BAD_DATA': bad += 1; continue
        item = msg.to_dict()
        item['source'] = [msg.get_srcSystem(), msg.get_srcComponent()]
        messages.append(item)
    return messages, bad
up, bad_up = decode(out / 'to_sitl_output.bin')
down, bad_down = decode(out / 'to_client_output.bin')
pick = lambda records, kind: [m for m in records if m['mavpackettype'] == kind]
points, fetches = pick(up, 'FENCE_POINT'), pick(up, 'FENCE_FETCH_POINT')
responses = pick(down, 'FENCE_POINT')
counts = [m for m in pick(down, 'MISSION_COUNT') if m['mission_type'] == 1]
requests = [m for m in pick(up, 'MISSION_REQUEST_INT') if m['mission_type'] == 1]
items = [m for m in pick(down, 'MISSION_ITEM_INT') if m['mission_type'] == 1]
heartbeats = [m for m in pick(down, 'HEARTBEAT') if m['source'] == [1, 1]]
assert [m['idx'] for m in points] == list(range(5))
assert [m['idx'] for m in fetches] == list(range(5)) * 2
assert [m['idx'] for m in responses] == list(range(5)) * 2
assert len(counts) == 1 and counts[0]['count'] == 4
assert [m['seq'] for m in requests] == list(range(4))
assert [m['seq'] for m in items] == list(range(4))
assert [m['command'] for m in items] == [5000, 5001, 5001, 5001]
assert [m['param1'] for m in items] == [0, 3, 3, 3]
expected = [(-35.363261,149.165230), (-35.364,149.164), (-35.362,149.164), (-35.363,149.167)]
def distance(lat1, lon1, lat2, lon2):
    a = math.sin(math.radians(lat2-lat1)/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(math.radians(lon2-lon1)/2)**2
    return 2 * 6371000 * math.asin(math.sqrt(a))
assert all(distance(m['x']/1e7, m['y']/1e7, *expected[i]) < 5 for i,m in enumerate(items))
assert heartbeats and all(not (m['base_mode'] & 128) for m in heartbeats)
assert (out / 'probe-retry-exit.txt').read_text().strip() == '0'
log = (out / 'probe-retry.log').read_text(encoding='utf8', errors='replace')
assert all(s in log for s in ['LEGACY_ROUNDTRIP=True', 'TYPED_COUNT=4', 'INTEROP_READ=True'])
summary = {'scope': 'One disarmed Copter 4.7.2 SITL run; legacy write then typed fence read',
           'relay': relay, 'points': points, 'fetches': fetches, 'responses': responses,
           'typed_counts': counts, 'typed_requests': requests, 'typed_items': items,
           'heartbeats': heartbeats, 'bad_data_fragments': {'uplink': bad_up, 'downlink': bad_down},
           'hashes': {name: sha(out / name) for name in ['probe-source.cs','probe.exe','probe.log','probe-exit.txt','probe-retry.log','probe-retry-exit.txt']},
           'library_hashes': {name: sha(root / 'mission-planner-portable' / name) for name in
                              ['MissionPlanner.ArduPilot.dll', 'MissionPlanner.Utilities.dll', 'MissionPlanner.Comms.dll', 'MAVLink.dll', 'Interfaces.dll', 'System.ValueTuple.dll', 'FenceLegacyInteropProbe.exe.config']}}
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print('Legacy points:', len(points), 'typed fence items:', len(items))
