"""Decode consecutive relay-generated progress and accepted ACK frames."""
import hashlib
import json
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega

def ack(data):
    msg = ardupilotmega.MAVLink(None).parse_char(data)
    assert msg is not None and msg.get_type() == 'COMMAND_ACK'
    return msg

def command(data):
    parser = ardupilotmega.MAVLink(None); parser.robust_parsing = True
    found = []
    for b in data:
        msg = parser.parse_char(bytes([b]))
        if msg is not None and msg.get_type() in ('COMMAND_LONG', 'COMMAND_INT') and msg.command == 510:
            found.append({'type': msg.get_type(), 'source': [msg.get_srcSystem(), msg.get_srcComponent()],
                          'target': [msg.target_system, msg.target_component], 'param1': msg.param1})
    return found

for form in ('long', 'int'):
    out = root / 'sitl-evidence' / ('command-progress-sequential-' + form)
    relay = json.loads((out / 'relay-result.json').read_text())
    assert relay['case'] == 'inject_progress_sequential' and relay['errors'] == [] and relay['closed_by'] == 'client'
    assert relay['injected_acks'] == relay['shifted_acks'] == 1 and relay['buffered_bytes_at_close'] == 0
    for name, digest in relay['capture_sha256'].items(): assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    original = (out / 'original_ack.bin').read_bytes()
    injected = (out / 'injected_ack.bin').read_bytes()
    shifted = (out / 'modified_ack.bin').read_bytes()
    assert len(original) == len(injected) == len(shifted) == 22
    assert original in (out / 'to_client_input.bin').read_bytes()
    assert injected + shifted in (out / 'to_client_output.bin').read_bytes()
    a, b, c = ack(original), ack(injected), ack(shifted)
    assert all((m.get_srcSystem(), m.get_srcComponent(), m.command, m.target_system, m.target_component) == (1, 1, 510, 255, 190) for m in (a, b, c))
    assert (a.result, b.result, c.result) == (0, 5, 0)
    assert b.get_seq() == a.get_seq() and c.get_seq() == (a.get_seq() + 1) % 256
    differences_progress = [i for i, (x, y) in enumerate(zip(original, injected)) if x != y]
    differences_shift = [i for i, (x, y) in enumerate(zip(original, shifted)) if x != y]
    assert differences_progress == [12, 20, 21] and differences_shift == [4, 20, 21]
    requests = command((out / 'to_sitl_output.bin').read_bytes())
    assert requests == [{'type': 'COMMAND_LONG' if form == 'long' else 'COMMAND_INT',
                         'source': [255, 190], 'target': [1, 1], 'param1': 30.0}]
    log = (out / 'probe.log').read_text(encoding='utf-16', errors='replace')
    lines = ['OPEN=True SELECTED=1:1', 'FORM=' + form + ' RESULT=' + ('True' if form == 'long' else 'False')]
    assert all(line in log for line in lines)
    summary = {'scope': 'Original library and disposable SITL; relay inserts progress and shifts accepted ACK sequence',
               'form': form, 'relay': relay, 'original_seq': a.get_seq(), 'progress_seq': b.get_seq(),
               'shifted_seq': c.get_seq(), 'original_result': 0, 'progress_result': 5, 'shifted_result': 0,
               'progress_differences': differences_progress, 'shifted_differences': differences_shift,
               'requests': requests, 'verified_probe_lines': lines}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(form, 'progress seq', b.get_seq(), 'accepted seq', c.get_seq(), 'result', form == 'long')
