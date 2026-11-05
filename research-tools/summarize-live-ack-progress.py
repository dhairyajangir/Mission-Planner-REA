"""Validate relay-inserted IN_PROGRESS and genuine ACK frames against captures."""
import hashlib
import json
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega

def parse_one(data):
    msg = ardupilotmega.MAVLink(None).parse_char(data)
    assert msg is not None and msg.get_type() == 'COMMAND_ACK'
    return msg

def requests(data):
    parser = ardupilotmega.MAVLink(None); parser.robust_parsing = True
    found = []
    for value in data:
        msg = parser.parse_char(bytes([value]))
        if msg is not None and msg.get_type() in ('COMMAND_LONG', 'COMMAND_INT') and msg.command == 510:
            found.append({'type': msg.get_type(), 'source': [msg.get_srcSystem(), msg.get_srcComponent()],
                          'target': [msg.target_system, msg.target_component], 'param1': msg.param1})
    return found

for form in ('long', 'int'):
    out = root / 'sitl-evidence' / ('command-progress-live-' + form)
    relay = json.loads((out / 'relay-result.json').read_text())
    assert relay['case'] == 'inject_progress' and relay['errors'] == [] and relay['injected_acks'] == 1
    assert relay['closed_by'] == 'client' and relay['buffered_bytes_at_close'] == 0
    for name, digest in relay['capture_sha256'].items(): assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    original = (out / 'original_ack.bin').read_bytes()
    injected = (out / 'injected_ack.bin').read_bytes()
    assert len(original) == len(injected) == 22 and original[0] == injected[0] == 0xfd
    assert original in (out / 'to_client_input.bin').read_bytes()
    assert injected + original in (out / 'to_client_output.bin').read_bytes()
    a, b = parse_one(original), parse_one(injected)
    assert (a.get_srcSystem(), a.get_srcComponent(), a.command, a.result, a.target_system, a.target_component) == (1, 1, 510, 0, 255, 190)
    assert (b.get_srcSystem(), b.get_srcComponent(), b.command, b.result, b.target_system, b.target_component) == (1, 1, 510, 5, 255, 190)
    assert a.get_seq() == b.get_seq()
    differences = [i for i, (x, y) in enumerate(zip(original, injected)) if x != y]
    assert differences == [12, 20, 21]
    request = requests((out / 'to_sitl_output.bin').read_bytes())
    assert request == [{'type': 'COMMAND_LONG' if form == 'long' else 'COMMAND_INT',
                        'source': [255, 190], 'target': [1, 1], 'param1': 30.0}]
    log = (out / 'probe.log').read_text(encoding='utf-16', errors='replace')
    lines = ['OPEN=True SELECTED=1:1', 'FORM=' + form + ' RESULT=' + ('True' if form == 'long' else 'False')]
    assert all(line in log for line in lines)
    summary = {'scope': 'Original library and disposable Copter SITL; relay inserts unsigned synthetic progress ACK',
               'form': form, 'relay': relay,
               'original': {'source': [1, 1], 'command': 510, 'result': 0, 'target': [255, 190], 'seq': a.get_seq()},
               'injected': {'source': [1, 1], 'command': 510, 'result': 5, 'target': [255, 190], 'seq': b.get_seq()},
               'byte_differences': differences, 'requests': request, 'verified_probe_lines': lines}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(form, 'result', form == 'long', 'same-sequence synthetic ACK before original')
