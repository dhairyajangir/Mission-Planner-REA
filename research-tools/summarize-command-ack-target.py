"""Independently decode and check synthetic MAVLink 2 ACK target-field fixtures."""
import hashlib
import json
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega

out = root / 'sitl-evidence/command-ack-target-synthetic'
manifest = json.loads((out / 'fixtures.json').read_text())
expected = {'wrong-target-then-denied': [(1, 1, 510, 0, 42, 17), (1, 1, 510, 2, 255, 190)],
            'matching-denied': [(1, 1, 510, 2, 255, 190)],
            'broadcast-accepted': [(1, 1, 510, 0, 0, 0)]}
log = (out / 'probe.log').read_text(encoding='utf-16')
cases = {}
for name, wanted in expected.items():
    data = (out / (name + '.bin')).read_bytes()
    assert len(data) == manifest[name]['bytes'] and hashlib.sha256(data).hexdigest() == manifest[name]['sha256']
    parser = ardupilotmega.MAVLink(None)
    frames = []
    for byte in data:
        msg = parser.parse_char(bytes([byte]))
        if msg is not None:
            assert msg.get_type() == 'COMMAND_ACK'
            frames.append((msg.get_srcSystem(), msg.get_srcComponent(), msg.command, msg.result,
                           msg.target_system, msg.target_component))
    assert frames == wanted
    result = name != 'matching-denied'
    remaining = 22 if name == 'wrong-target-then-denied' else 0
    lines = ['FORM=%s CASE=%s RESULT=%s REMAINING=%d GIVE=False' % (form, name, str(result), remaining)
             for form in ('long', 'int')]
    assert all(line in log for line in lines)
    cases[name] = {'frames': frames, 'result': result, 'remaining': remaining, 'lines': lines}
(out / 'summary.json').write_text(json.dumps({'scope': 'Synthetic MAVLink 2 ACK target fields; original library; no vehicle',
                                               'fixtures': manifest, 'cases': cases}, indent=2) + '\n')
print('verified', len(cases), 'ACK target fixtures for both command forms')
