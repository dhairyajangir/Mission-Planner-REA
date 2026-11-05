"""Check original-library reconnect logs against independent MAVLink decoding."""
import hashlib
import json
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parent.parent
run = root / 'sitl-evidence/mavlink-reconnect-probe'
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega

def decode(path):
    parser = ardupilotmega.MAVLink(None)
    parser.robust_parsing = True
    messages, bad = [], 0
    for byte in path.read_bytes():
        msg = parser.parse_char(bytes([byte]))
        if msg is None: continue
        if msg.get_type() == 'BAD_DATA': bad += 1; continue
        if msg.get_type() in ('HEARTBEAT', 'PARAM_REQUEST_READ', 'PARAM_VALUE'):
            item = msg.to_dict()
            item['source_system'] = msg.get_srcSystem()
            item['source_component'] = msg.get_srcComponent()
            messages.append(item)
    return messages, bad

relay = json.loads((run / 'relay-result.json').read_text())
assert relay['errors'] == []
assert relay['events'] == ['session1_accept', 'session1_reset', 'session2_accept', 'session2_client_eof']
for name, digest in relay['captures_sha256'].items():
    assert hashlib.sha256((run / name).read_bytes()).hexdigest() == digest
log = (run / 'probe.log').read_text(encoding='utf-16', errors='replace')
expected = ['FIRST_OPEN=True SELECTED=1:1', 'FIRST_PARAM=0', 'AFTER_DROP_BEFORE_CLOSE_OPEN=True',
            'SECOND_OPEN=True SELECTED=1:1', 'SECOND_PARAM=0']
for item in expected: assert item in log, item
sessions = []
for number in (1, 2):
    up, up_bad = decode(run / ('uplink%d.bin' % number))
    down, down_bad = decode(run / ('downlink%d.bin' % number))
    requests = [m for m in up if m['mavpackettype'] == 'PARAM_REQUEST_READ' and m['param_id'] == 'LOG_DISARMED']
    values = [m for m in down if m['mavpackettype'] == 'PARAM_VALUE' and m['param_id'] == 'LOG_DISARMED']
    assert any(m['target_system'] == 1 and m['target_component'] == 1 for m in requests)
    assert any(m['source_system'] == 1 and m['source_component'] == 1 and m['param_value'] == 0 for m in values)
    assert any(m['mavpackettype'] == 'HEARTBEAT' and m['source_system'] == 1 for m in down)
    sessions.append({'number': number, 'requests': requests, 'values': values,
                     'bad_data_fragments': {'uplink': up_bad, 'downlink': down_bad}})
summary = {'scope': 'Original Mission Planner MAVLink library; forced relay reset and explicit reopen; one disposable SITL',
           'relay': relay, 'verified_probe_lines': expected, 'sessions': sessions}
(run / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps({'sessions': len(sessions), 'bad_data_fragments': [s['bad_data_fragments'] for s in sessions]}))
