"""Validate bytes drained after COMMAND_INT returns in an injected-ACK test."""
import hashlib
import json
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega
out = root / 'sitl-evidence/command-progress-drain-int'
relay = json.loads((out / 'relay-result.json').read_text())
assert relay['case'] == 'inject_progress_drain' and relay['errors'] == [] and relay['closed_by'] == 'client'
assert relay['injected_acks'] == relay['shifted_acks'] == 1
for name, digest in relay['capture_sha256'].items(): assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
drain = (out / 'drain.bin').read_bytes()
original = (out / 'original_ack.bin').read_bytes()
progress = (out / 'injected_ack.bin').read_bytes()
accepted = (out / 'modified_ack.bin').read_bytes()
assert progress + accepted in (out / 'to_client_output.bin').read_bytes()
assert accepted in drain
parser = ardupilotmega.MAVLink(None); parser.robust_parsing = True
acks, bad = [], 0
for byte in drain:
    msg = parser.parse_char(bytes([byte]))
    if msg is None: continue
    if msg.get_type() == 'BAD_DATA': bad += 1; continue
    if msg.get_type() == 'COMMAND_ACK' and msg.command == 510:
        acks.append({'source': [msg.get_srcSystem(), msg.get_srcComponent()], 'target': [msg.target_system, msg.target_component],
                     'command': msg.command, 'result': msg.result, 'seq': msg.get_seq(),
                     'raw_sha256': hashlib.sha256(bytes(msg.get_msgbuf())).hexdigest()})
assert len(acks) == 1 and acks[0]['result'] == 0 and acks[0]['source'] == [1, 1] and acks[0]['target'] == [255, 190]
assert acks[0]['raw_sha256'] == hashlib.sha256(accepted).hexdigest()
initial = ardupilotmega.MAVLink(None).parse_char(original)
injected = ardupilotmega.MAVLink(None).parse_char(progress)
assert initial.result == 0 and injected.result == 5 and injected.get_seq() == initial.get_seq()
assert acks[0]['seq'] == (initial.get_seq() + 1) % 256
log = (out / 'probe.log').read_text(encoding='utf-16', errors='replace')
lines = ['OPEN=True SELECTED=1:1', 'INT_RESULT=False', 'DRAIN_BYTES=' + str(len(drain))]
assert all(line in log for line in lines)
summary = {'scope': 'Original COMMAND_INT with relay-injected progress; capture of post-return TCP bytes',
           'relay': relay, 'drain_sha256': hashlib.sha256(drain).hexdigest(), 'drain_bytes': len(drain),
           'decoded_acks': acks, 'bad_data_fragments': bad, 'verified_probe_lines': lines}
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print('drained', len(drain), 'bytes; accepted ACKs', len(acks), 'bad fragments', bad)
