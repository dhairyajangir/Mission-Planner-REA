"""Independently decode two COMMAND_INT requests with a dropped second ACK."""
import hashlib
import json
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega
out = root / 'sitl-evidence/command-stale-ack-int'
relay = json.loads((out / 'relay-result.json').read_text())
assert relay['case'] == 'stale_ack_test' and relay['errors'] == [] and relay['closed_by'] == 'client'
assert relay['injected_acks'] == relay['shifted_acks'] == relay['dropped_acks'] == 1
assert relay['command_events'] == ['request1', 'first_progress_and_accepted_forwarded', 'request2', 'second_ack_dropped']
for name, digest in relay['capture_sha256'].items(): assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
def decode(path):
    parser = ardupilotmega.MAVLink(None); parser.robust_parsing = True
    found, bad = [], 0
    for byte in path.read_bytes():
        msg = parser.parse_char(bytes([byte]))
        if msg is None: continue
        if msg.get_type() == 'BAD_DATA': bad += 1; continue
        if msg.get_type() in ('COMMAND_INT', 'COMMAND_ACK') and msg.command == 510:
            item = msg.to_dict(); item['source'] = [msg.get_srcSystem(), msg.get_srcComponent()]
            item['seq'] = msg.get_seq(); item['raw_sha256'] = hashlib.sha256(bytes(msg.get_msgbuf())).hexdigest()
            found.append(item)
    return found, bad
requests, up_bad = decode(out / 'to_sitl_output.bin')
sim_acks, in_bad = decode(out / 'to_client_input.bin')
forwarded, out_bad = decode(out / 'to_client_output.bin')
dropped, drop_bad = decode(out / 'dropped.bin')
assert len(requests) == 2 and all(m['mavpackettype'] == 'COMMAND_INT' and m['target_system'] == 1 and
    m['target_component'] == 1 and m['param1'] == 30 for m in requests)
assert len(sim_acks) == 2 and all(m['result'] == 0 and m['source'] == [1, 1] for m in sim_acks)
assert len(forwarded) == 2 and [m['result'] for m in forwarded] == [5, 0]
assert all(m['source'] == [1, 1] and m['target_system'] == 255 and m['target_component'] == 190 for m in forwarded)
assert len(dropped) == 1 and dropped[0]['raw_sha256'] == sim_acks[1]['raw_sha256']
assert forwarded[0]['seq'] == sim_acks[0]['seq'] and forwarded[1]['seq'] == (sim_acks[0]['seq'] + 1) % 256
assert forwarded[0]['raw_sha256'] == hashlib.sha256((out / 'injected_ack.bin').read_bytes()).hexdigest()
assert forwarded[1]['raw_sha256'] == hashlib.sha256((out / 'modified_ack.bin').read_bytes()).hexdigest()
assert sim_acks[0]['raw_sha256'] == hashlib.sha256((out / 'original_ack.bin').read_bytes()).hexdigest()
log = (out / 'probe.log').read_text(encoding='utf-16', errors='replace')
lines = ['OPEN=True SELECTED=1:1', 'FIRST_RESULT=False', 'SECOND_RESULT=True']
assert all(line in log for line in lines)
summary = {'scope': 'Two identical read-only COMMAND_INT requests; local relay inserts progress and drops second ACK',
           'relay': relay, 'requests': requests, 'simulator_acks': sim_acks, 'forwarded_acks': forwarded, 'dropped_acks': dropped,
           'bad_data_fragments': {'uplink': up_bad, 'downlink_input': in_bad, 'downlink_output': out_bad, 'dropped': drop_bad},
           'verified_probe_lines': lines}
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print('two requests; first ACK pair forwarded before second request; second ACK dropped; library results false then true')
