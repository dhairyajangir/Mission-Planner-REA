"""Decode and check the disarmed accelerometer calibration start capture."""
import hashlib
import json
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega

out = root / 'sitl-evidence/command-ack-calibration_start'
relay = json.loads((out / 'relay-result.json').read_text())
assert relay['case'] == 'calibration_start' and relay['errors'] == []
assert relay['closed_by'] == 'client' and relay['buffered_bytes_at_close'] == 0
for name, digest in relay['capture_sha256'].items():
    assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest

def decode(name):
    parser = ardupilotmega.MAVLink(None)
    parser.robust_parsing = True
    messages, bad = [], 0
    for byte in (out / name).read_bytes():
        msg = parser.parse_char(bytes([byte]))
        if msg is None:
            continue
        if msg.get_type() == 'BAD_DATA':
            bad += 1
        elif msg.get_type() in ('HEARTBEAT', 'COMMAND_LONG', 'COMMAND_ACK'):
            item = msg.to_dict()
            item['source'] = [msg.get_srcSystem(), msg.get_srcComponent()]
            messages.append(item)
    return messages, bad

up, bad_up = decode('to_sitl_output.bin')
down, bad_down = decode('to_client_output.bin')
start = [m for m in up if m['mavpackettype'] == 'COMMAND_LONG' and m['command'] == 241]
assert len(start) == 1 and start[0]['target_system'] == 1 and start[0]['target_component'] == 1
assert [start[0]['param' + str(i)] for i in range(1, 8)] == [0, 0, 0, 0, 1, 0, 0]
responses = [m for m in down if m['mavpackettype'] == 'COMMAND_ACK' and m['command'] == 241]
assert responses and all(m['source'] == [1, 1] and m['result'] == 0 for m in responses)
positions = [m for m in down if m['mavpackettype'] == 'COMMAND_LONG' and m['command'] == 42429]
assert len(positions) >= 2 and all(m['source'] == [1, 1] and m['param1'] == 1 for m in positions)
assert not [m for m in up if m['mavpackettype'] == 'COMMAND_LONG' and m['command'] == 42429]
heartbeats = [m for m in down if m['mavpackettype'] == 'HEARTBEAT' and m['source'] == [1, 1]]
assert heartbeats and all(not (m['base_mode'] & 128) for m in heartbeats)
log = (out / 'probe.log').read_text(encoding='utf-8')
lines = ['OPEN=True SELECTED=1:1', 'INITIAL_ARMED=False', 'PREFLIGHT_CALIBRATION_RETURN=True', 'POSITION_REQUEST=1', 'POSITION_REQUEST_COUNT=12']
assert all(line in log for line in lines)
binary = root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll'
summary = {'scope': 'Original Mission Planner library; disarmed source-built Copter SITL; calibration not completed',
           'relay': relay, 'library_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
           'start': start, 'acknowledgements': responses, 'position_requests': positions, 'heartbeats': heartbeats,
           'bad_data_fragments': {'uplink': bad_up, 'downlink': bad_down}, 'verified_probe_lines': lines}
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print('Accepted start;', len(positions), 'level requests; no position confirmation')
