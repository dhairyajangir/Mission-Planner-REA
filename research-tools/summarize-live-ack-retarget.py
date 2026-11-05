"""Verify relay-retargeted ACKs and original-library results against SITL captures."""
import hashlib
import json
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega

def decode_one(data):
    parser = ardupilotmega.MAVLink(None)
    msg = parser.parse_char(data)
    assert msg is not None and msg.get_type() == 'COMMAND_ACK'
    return msg

def decode_requests(data):
    parser = ardupilotmega.MAVLink(None); parser.robust_parsing = True
    found = []
    for value in data:
        msg = parser.parse_char(bytes([value]))
        if msg is not None and msg.get_type() in ('COMMAND_LONG', 'COMMAND_INT') and msg.command == 510:
            found.append({'type': msg.get_type(), 'source': [msg.get_srcSystem(), msg.get_srcComponent()],
                          'target': [msg.target_system, msg.target_component], 'param1': msg.param1})
    return found

for form in ('long', 'int'):
    out = root / 'sitl-evidence' / ('command-target-live-' + form)
    relay = json.loads((out / 'relay-result.json').read_text())
    assert relay['case'] == 'retarget' and relay['errors'] == [] and relay['retargeted_acks'] == 1
    assert relay['closed_by'] == 'client' and relay['buffered_bytes_at_close'] == 0
    for name, digest in relay['capture_sha256'].items(): assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    before = (out / 'original_ack.bin').read_bytes()
    after = (out / 'modified_ack.bin').read_bytes()
    assert len(before) == len(after) == 22 and before[0] == after[0] == 0xfd
    assert before in (out / 'to_client_input.bin').read_bytes()
    assert after in (out / 'to_client_output.bin').read_bytes()
    left, right = decode_one(before), decode_one(after)
    assert (left.get_srcSystem(), left.get_srcComponent(), left.command, left.result, left.target_system, left.target_component) == (1, 1, 510, 0, 255, 190)
    assert (right.get_srcSystem(), right.get_srcComponent(), right.command, right.result, right.target_system, right.target_component) == (1, 1, 510, 0, 42, 17)
    assert left.get_seq() == right.get_seq()
    differences = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    assert set(differences).issubset({18, 19, 20, 21}) and {18, 19}.issubset(differences)
    requests = decode_requests((out / 'to_sitl_output.bin').read_bytes())
    assert requests == [{'type': 'COMMAND_LONG' if form == 'long' else 'COMMAND_INT',
                         'source': [255, 190], 'target': [1, 1], 'param1': 30.0}]
    log = (out / 'probe.log').read_text(encoding='utf-16', errors='replace')
    lines = ['OPEN=True SELECTED=1:1', 'COMMAND_RESULT=True']
    assert all(line in log for line in lines)
    summary = {'scope': 'Original library and disposable Copter SITL; relay rewrites one unsigned ACK target and CRC',
               'form': form, 'relay': relay, 'original': {'source': [1, 1], 'command': 510, 'result': 0, 'target': [255, 190], 'seq': left.get_seq()},
               'modified': {'source': [1, 1], 'command': 510, 'result': 0, 'target': [42, 17], 'seq': right.get_seq()},
               'byte_differences': differences, 'requests': requests, 'verified_probe_lines': lines}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(form, 'accepted rewritten ACK; byte differences', differences)
