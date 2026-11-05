"""Decode captured client packets; does not infer aircraft movement."""
from pathlib import Path
import hashlib, json, os, sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega as mavlink
run = root / 'sitl-evidence/command-ack-guided_position'
raw = (run / 'to_sitl_output.bin').read_bytes()
parser = mavlink.MAVLink(None)
parser.robust_parsing = True
packets = []
for b in raw:
    m = parser.parse_char(bytes([b]))
    if m and m.get_type() != 'BAD_DATA':
        packets.append(m)
targets = [m.to_dict() for m in packets if m.get_type() == 'SET_POSITION_TARGET_GLOBAL_INT']
mode_indices = [i for i, m in enumerate(packets) if m.get_type() == 'SET_MODE']
target_indices = [i for i, m in enumerate(packets) if m.get_type() == 'SET_POSITION_TARGET_GLOBAL_INT']
assert len(targets) == 2, targets
assert target_indices[0] < min(mode_indices) < target_indices[1]
for t, lat, lon, alt in zip(targets, (-353631000, -353632000), (1491651000, 1491652000), (11, 12)):
    assert abs(t['lat_int'] - lat) <= 1 and abs(t['lon_int'] - lon) <= 1, t
    assert t['alt'] == alt and t['target_system'] == 1 and t['target_component'] == 1, t
assert targets[0]['type_mask'] == targets[1]['type_mask']
assert targets[0]['coordinate_frame'] == targets[1]['coordinate_frame']
assert (run / 'probe-exit.txt').read_text().strip() == '0'
relay = json.loads((run / 'relay-result.json').read_text())
assert not relay['errors']
assert hashlib.sha256(raw).hexdigest() == relay['capture_sha256']['to_sitl_output.bin']
summary = {'scope': 'disarmed SITL; packet observations only', 'targets': targets,
           'target_packet_indices': target_indices, 'set_mode_packet_indices': mode_indices,
           'capture_sha256': hashlib.sha256(raw).hexdigest(), 'probe_exit': 0}
(run / 'guided-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
