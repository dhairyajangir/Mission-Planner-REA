"""Decode the simulator's replies to two unsupported-command request forms."""
import hashlib
import json
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega
out = root / 'sitl-evidence/command-unsupported-normal'
relay = json.loads((out / 'relay-result.json').read_text())
assert relay['errors'] == [] and relay['closed_by'] == 'client' and relay['dropped_acks'] == 0
for name, digest in relay['capture_sha256'].items(): assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
def decode(path):
    parser = ardupilotmega.MAVLink(None); parser.robust_parsing = True
    found, bad = [], 0
    for byte in path.read_bytes():
        msg = parser.parse_char(bytes([byte]))
        if msg is None: continue
        if msg.get_type() == 'BAD_DATA': bad += 1; continue
        if msg.get_type() in ('COMMAND_LONG', 'COMMAND_INT', 'COMMAND_ACK') and msg.command == 65530:
            item = msg.to_dict(); item['source_system'] = msg.get_srcSystem(); item['source_component'] = msg.get_srcComponent()
            found.append(item)
    return found, bad
requests, up_bad = decode(out / 'to_sitl_output.bin')
acks, down_bad = decode(out / 'to_client_output.bin')
assert [m['mavpackettype'] for m in requests] == ['COMMAND_LONG', 'COMMAND_INT']
assert all(m['target_system'] == 1 and m['target_component'] == 1 for m in requests)
assert len(acks) == 2 and all(m['result'] == 3 and m['source_system'] == 1 and m['source_component'] == 1 for m in acks)
log = (out / 'probe.log').read_text(encoding='utf-16', errors='replace')
lines = ['OPEN=True SELECTED=1:1', 'LONG_RESULT=False', 'INT_RESULT=False']
assert all(line in log for line in lines)
summary = {'scope': 'Unknown command 65530, both forms, original library and disposable source-built SITL',
           'relay_scope_correction': 'relay-result.json scope describes interval request but this case sent command 65530',
           'relay': relay, 'requests': requests, 'acks': acks,
           'bad_data_fragments': {'uplink': up_bad, 'downlink': down_bad}, 'verified_probe_lines': lines}
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print('requests', len(requests), 'unsupported ACKs', len(acks), 'bad fragments', down_bad)
