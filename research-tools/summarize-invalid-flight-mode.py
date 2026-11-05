"""Decode invalid mode request and SITL responses from saved captures."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega
out = root / 'sitl-evidence/flight-mode-invalid'
relay = json.loads((out / 'relay-result.json').read_text())
assert relay['case'] == 'mode_invalid' and relay['errors'] == [] and relay['closed_by'] == 'client'
assert relay['mode_packets'] == {'command_seen': 1, 'command_dropped': 0, 'legacy_seen': 2, 'legacy_dropped': 0}
for name, digest in relay['capture_sha256'].items(): assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
def decode(path):
    parser = ardupilotmega.MAVLink(None); parser.robust_parsing = True
    found, bad = [], 0
    for b in path.read_bytes():
        msg = parser.parse_char(bytes([b]))
        if msg is None: continue
        if msg.get_type() == 'BAD_DATA': bad += 1; continue
        if msg.get_type() in ('HEARTBEAT', 'SET_MODE', 'COMMAND_LONG', 'COMMAND_ACK'):
            item = msg.to_dict(); item['source'] = [msg.get_srcSystem(), msg.get_srcComponent()]
            found.append(item)
    return found, bad
up, up_bad = decode(out / 'to_sitl_output.bin')
down, down_bad = decode(out / 'to_client_output.bin')
sent = [m for m in up if m['mavpackettype'] == 'SET_MODE' or (m['mavpackettype'] == 'COMMAND_LONG' and m['command'] == 176)]
acks = [m for m in down if m['mavpackettype'] == 'COMMAND_ACK' and m['command'] == 176 and m['source'] == [1, 1]]
heartbeats = [m for m in down if m['mavpackettype'] == 'HEARTBEAT' and m['source'] == [1, 1]]
assert [m['mavpackettype'] for m in sent] == ['COMMAND_LONG', 'SET_MODE', 'SET_MODE']
assert sent[0]['param1'] == 1 and sent[0]['param2'] == 999 and sent[0]['target_system'] == 1 and sent[0]['target_component'] == 1
assert all(m['custom_mode'] == 999 and m['base_mode'] == 1 and m['target_system'] == 1 for m in sent[1:])
assert heartbeats and all(m['custom_mode'] == 0 and (m['base_mode'] & 128) == 0 for m in heartbeats)
assert acks and all(m['result'] == 4 for m in acks)
log = (out / 'probe.log').read_text(encoding='utf-16', errors='replace')
lines = ['OPEN=True SELECTED=1:1', 'INITIAL_MODE=0 ARMED=False', 'INVALID_MODE_CALL_RETURNED']
assert all(line in log for line in lines)
match = re.search(r'FINAL_MODE=0 ARMED=False HEARTBEATS=(\d+)', log)
assert match and int(match.group(1)) > 0
lines.append(match.group(0))
summary = {'scope': 'Original library requests invalid numeric mode 999 from disposable disarmed Copter SITL',
           'relay': relay, 'sent': sent, 'acks': acks, 'heartbeats': heartbeats,
           'bad_data_fragments': {'uplink': up_bad, 'downlink': down_bad}, 'verified_probe_lines': lines}
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print('sent', len(sent), 'failed ACKs', len(acks), 'disarmed heartbeats', len(heartbeats))
