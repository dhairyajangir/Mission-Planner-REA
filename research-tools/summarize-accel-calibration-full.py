"""Decode six-position calibration-model SITL evidence."""
import hashlib
import json
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega
out = root / 'sitl-evidence/command-ack-calibration_full'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
relay = json.loads((out / 'relay-result.json').read_text())
assert relay['case'] == 'calibration_full' and relay['errors'] == []
assert relay['closed_by'] == 'client' and relay['buffered_bytes_at_close'] == 0
for name, digest in relay['capture_sha256'].items(): assert sha(out / name) == digest
relay_source = (out / 'relay-source.py').read_text(encoding='utf-8')
assert "'calibration' if case == 'calibration_full' else 'quad'" in relay_source
def decode(name):
    parser = ardupilotmega.MAVLink(None)
    parser.robust_parsing = True
    result, bad = [], 0
    for byte in (out / name).read_bytes():
        msg = parser.parse_char(bytes([byte]))
        if msg is None: continue
        if msg.get_type() == 'BAD_DATA': bad += 1
        elif msg.get_type() in ('HEARTBEAT', 'COMMAND_LONG', 'COMMAND_ACK', 'STATUSTEXT'):
            item = msg.to_dict(); item['source'] = [msg.get_srcSystem(), msg.get_srcComponent()]
            result.append(item)
    return result, bad
up, bad_up = decode('to_sitl_output.bin')
down, bad_down = decode('to_client_output.bin')
start = [m for m in up if m['mavpackettype'] == 'COMMAND_LONG' and m['command'] == 241]
assert len(start) == 1 and [start[0]['param' + str(i)] for i in range(1, 8)] == [0, 0, 0, 0, 1, 0, 0]
start_acks = [m for m in down if m['mavpackettype'] == 'COMMAND_ACK' and m['command'] == 241]
assert len(start_acks) == 1 and start_acks[0]['source'] == [1, 1] and start_acks[0]['result'] == 0
responses = [m for m in up if m['mavpackettype'] == 'COMMAND_LONG' and m['command'] == 42429]
assert [m['param1'] for m in responses] == list(range(1, 7))
assert all(m['target_system'] == 0 and m['target_component'] == 0 for m in responses)
servo = [m for m in up if m['mavpackettype'] == 'COMMAND_LONG' and m['command'] == 183]
assert len(servo) == 22
servo_acks = [m for m in down if m['mavpackettype'] == 'COMMAND_ACK' and m['command'] == 183]
assert len(servo_acks) == 22 and all(m['source'] == [1, 1] and m['result'] == 0 for m in servo_acks)
events = [m for m in down if m.get('command') == 42429 and m['mavpackettype'] in ('COMMAND_ACK', 'COMMAND_LONG')]
acks = [m for m in events if m['mavpackettype'] == 'COMMAND_ACK']
positions = [m for m in events if m['mavpackettype'] == 'COMMAND_LONG']
assert len(acks) == 6 and all(m['result'] == 0 and m['source'] == [1, 1] for m in acks)
assert sorted(set(m['param1'] for m in positions)) == list(range(1, 7))
success = [m for m in down if m['mavpackettype'] == 'STATUSTEXT' and 'Calibration successful' in m['text']]
assert success and all(m['source'] == [1, 1] for m in success)
heartbeats = [m for m in down if m['mavpackettype'] == 'HEARTBEAT' and m['source'] == [1, 1]]
assert heartbeats and all(not (m['base_mode'] & 128) for m in heartbeats)
log = (out / 'probe.log').read_text(encoding='utf-8')
lines = ['INITIAL_ARMED=False', 'START_RETURN=True']
for position in range(1, 7): lines += ['REQUEST=' + str(position), 'POSE=' + str(position), 'CONFIRMED=' + str(position)]
lines += ['STATUS=Calibration successful', 'RESULT=SUCCESS_TEXT']
assert all(line in log for line in lines) and [log.index(line) for line in lines] == sorted(log.index(line) for line in lines)
result = {'scope': 'Original Mission Planner library; disarmed Copter calibration model; no UI or physical sensor',
          'relay': relay, 'library_sha256': sha(root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll'),
          'relay_source_sha256': sha(out / 'relay-source.py'), 'probe_source_sha256': sha(out / 'probe-source.cs'),
          'start': start, 'start_acks': start_acks, 'position_responses': responses, 'position_events': events,
          'servo_commands': servo, 'servo_acks': servo_acks, 'success_messages': success, 'heartbeats': heartbeats,
          'bad_data_fragments': {'uplink': bad_up, 'downlink': bad_down}, 'verified_probe_lines': lines}
(out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
print('Six position responses accepted; simulator reported success')
