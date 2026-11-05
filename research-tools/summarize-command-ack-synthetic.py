"""Decode synthetic ACKs independently and check the original library log."""
import hashlib
import json
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
from pymavlink.dialects.v10 import ardupilotmega

out = root / 'sitl-evidence/command-ack-synthetic'
manifest = json.loads((out / 'fixtures.json').read_text())
expected = {
    'wrong-system': ([(2, 1, 510, 0), (1, 1, 510, 2)], False, 0),
    'wrong-component': ([(1, 2, 510, 0), (1, 1, 510, 2)], False, 0),
    'wrong-command': ([(1, 1, 511, 0), (1, 1, 510, 2)], False, 0),
    'in-progress': ([(1, 1, 510, 5), (1, 1, 510, 0)], True, 0),
    'denied': ([(1, 1, 510, 2)], False, 0),
    'no-ack': ([(1, 1, 510, 2)], True, 11),
}
log = (out / 'probe.log').read_text(encoding='utf-16')
observed = {}
for name, (frames, answer, remaining) in expected.items():
    data = (out / (name + '.bin')).read_bytes()
    assert len(data) == manifest[name]['bytes'] and hashlib.sha256(data).hexdigest() == manifest[name]['sha256']
    parser = ardupilotmega.MAVLink(None)
    parsed = []
    for byte in data:
        msg = parser.parse_char(bytes([byte]))
        if msg is not None:
            assert msg.get_type() == 'COMMAND_ACK'
            parsed.append((msg.get_srcSystem(), msg.get_srcComponent(), msg.command, msg.result))
    assert parsed == frames
    line = 'CASE=%s RESULT=%s REMAINING=%d GIVE=False' % (name, str(answer), remaining)
    assert line in log
    observed[name] = {'frames': parsed, 'result': answer, 'remaining': remaining, 'probe_line': line}
summary = {'scope': 'Original library with synthetic in-memory MAVLink 1 ACK packets; no socket or vehicle',
           'fixtures': manifest, 'cases': observed}
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print('verified', len(observed), 'synthetic ACK cases')
