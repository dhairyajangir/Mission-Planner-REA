"""Independently decode captured relay frames and cross-check probe output."""
import hashlib
import json
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parent.parent
out = root / 'sitl-evidence' / 'dual-sitl-library-attempt3'
sys.path.insert(0, str(root / 'sitl-evidence' / 'python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega

def decode(path):
    parser = ardupilotmega.MAVLink(None)
    parser.robust_parsing = True
    messages = []
    for b in path.read_bytes():
        msg = parser.parse_char(bytes([b]))
        if msg is None: continue
        if msg.get_type() == 'BAD_DATA': raise ValueError('invalid forwarded frame in ' + str(path))
        if msg.get_type() in ('HEARTBEAT', 'PARAM_REQUEST_READ', 'PARAM_VALUE', 'PARAM_SET'):
            d = msg.to_dict()
            d['source_system'] = msg.get_srcSystem()
            d['source_component'] = msg.get_srcComponent()
            messages.append(d)
    return messages

relay = json.loads((out / 'relay-result.json').read_text())
for name, expected in relay['sha256'].items():
    assert hashlib.sha256((out / name).read_bytes()).hexdigest() == expected
up, down = decode(out / 'uplink.bin'), decode(out / 'downlink.bin')
params = [m for m in down if m['mavpackettype'] == 'PARAM_VALUE' and m['param_id'] == 'LOG_DISARMED']
requests = [m for m in up if m['mavpackettype'] in ('PARAM_SET', 'PARAM_REQUEST_READ') and m['param_id'] == 'LOG_DISARMED']
text = (out / 'probe.log').read_text(encoding='utf-16', errors='replace')
expected_lines = ['OPEN=True', 'SEEN_1=True SEEN_2=True', 'DIRECT_1=0 DIRECT_2=1',
                  'SELECTED_1=0 SELECTED_2=1', 'CACHE_1=0 CACHE_2=1', 'RESTORE_2=True READBACK_2=0']
for line in expected_lines: assert line in text, line
assert relay['errors'] == [] and relay['ended_by'] == 'client_eof'
assert {(m['source_system'], m['param_value']) for m in params} >= {(1, 0.0), (2, 1.0), (2, 0.0)}
assert {m['target_system'] for m in requests if m['mavpackettype'] == 'PARAM_REQUEST_READ'} >= {1, 2}
assert any(m['mavpackettype'] == 'PARAM_SET' and m['target_system'] == 2 and m['param_value'] == 0 for m in requests)
summary = {'scope': 'Two disposable source-built Copter SITL instances; frame-aware local relay; original Mission Planner library',
           'relay': relay, 'verified_probe_lines': expected_lines, 'requests': requests, 'parameter_responses': params,
           'heartbeat_systems': sorted({m['source_system'] for m in down if m['mavpackettype'] == 'HEARTBEAT'})}
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps({'heartbeat_systems': summary['heartbeat_systems'], 'requests': len(requests), 'responses': len(params)}))
