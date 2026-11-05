"""Decode the wrong-then-correct position response in disarmed SITL."""
import hashlib
import json
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega
out = root / 'sitl-evidence/command-ack-calibration_step'
relay = json.loads((out / 'relay-result.json').read_text())
assert relay['case'] == 'calibration_step' and relay['errors'] == []
assert relay['closed_by'] == 'client' and relay['buffered_bytes_at_close'] == 0
for name, digest in relay['capture_sha256'].items():
    assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
def decode(name):
    parser = ardupilotmega.MAVLink(None)
    parser.robust_parsing = True
    messages, bad = [], 0
    for byte in (out / name).read_bytes():
        msg = parser.parse_char(bytes([byte]))
        if msg is None: continue
        if msg.get_type() == 'BAD_DATA': bad += 1
        elif msg.get_type() in ('HEARTBEAT', 'COMMAND_LONG', 'COMMAND_ACK'):
            item = msg.to_dict()
            item['source'] = [msg.get_srcSystem(), msg.get_srcComponent()]
            messages.append(item)
    return messages, bad
up, bad_up = decode('to_sitl_output.bin')
down, bad_down = decode('to_client_output.bin')
start = [m for m in up if m['mavpackettype'] == 'COMMAND_LONG' and m['command'] == 241]
assert len(start) == 1 and [start[0]['param' + str(i)] for i in range(1, 8)] == [0, 0, 0, 0, 1, 0, 0]
sent = [m for m in up if m['mavpackettype'] == 'COMMAND_LONG' and m['command'] == 42429]
assert [m['param1'] for m in sent] == [2, 1] and all(m['target_system'] == 0 and m['target_component'] == 0 for m in sent)
events = [m for m in down if (m['mavpackettype'] == 'COMMAND_LONG' or m['mavpackettype'] == 'COMMAND_ACK') and m['command'] == 42429]
assert [(m['mavpackettype'], m.get('param1'), m.get('result')) for m in events] == [
    ('COMMAND_LONG', 1, None), ('COMMAND_ACK', None, 4), ('COMMAND_LONG', 1, None),
    ('COMMAND_LONG', 1, None), ('COMMAND_LONG', 1, None), ('COMMAND_ACK', None, 0), ('COMMAND_LONG', 2, None)]
assert all(m['source'] == [1, 1] for m in events)
heartbeats = [m for m in down if m['mavpackettype'] == 'HEARTBEAT' and m['source'] == [1, 1]]
assert heartbeats and all(not (m['base_mode'] & 128) for m in heartbeats)
log = (out / 'probe.log').read_text(encoding='utf-8')
lines = ['INITIAL_ARMED=False', 'START_RETURN=True', 'POSITION_REQUEST=1 PHASE=0', 'SENT_POSITION=2',
         'POSITION_REQUEST=1 PHASE=1', 'SENT_POSITION=1', 'POSITION_REQUEST=2 PHASE=2', 'NEXT_POSITION=2']
assert all(line in log for line in lines) and [log.index(line) for line in lines] == sorted(log.index(line) for line in lines)
summary = {'scope': 'Original Mission Planner library; disarmed Copter SITL; first orientation only',
           'relay': relay, 'library_sha256': hashlib.sha256((root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll').read_bytes()).hexdigest(),
           'start': start, 'position_responses': sent, 'position_events': events, 'heartbeats': heartbeats,
           'bad_data_fragments': {'uplink': bad_up, 'downlink': bad_down}, 'verified_probe_lines': lines}
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print('Wrong position failed; level accepted; next position requested')
