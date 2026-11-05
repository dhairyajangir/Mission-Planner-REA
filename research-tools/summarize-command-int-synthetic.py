"""Check COMMAND_INT results against already-decoded synthetic ACK fixtures."""
import hashlib
import json
from pathlib import Path
root = Path(__file__).resolve().parent.parent
out = root / 'sitl-evidence/command-ack-synthetic'
long_summary = json.loads((out / 'summary.json').read_text())
log = (out / 'probe-int.log').read_text(encoding='utf-16')
cases = {}
for name, original in long_summary['cases'].items():
    data = (out / (name + '.bin')).read_bytes()
    assert hashlib.sha256(data).hexdigest() == long_summary['fixtures'][name]['sha256']
    result = name == 'no-ack'
    remaining = 11 if name in ('no-ack', 'in-progress') else 0
    line = 'CASE=%s RESULT=%s REMAINING=%d GIVE=False' % (name, str(result), remaining)
    assert line in log
    cases[name] = {'frames': original['frames'], 'result': result, 'remaining': remaining, 'probe_line': line}
(out / 'summary-int.json').write_text(json.dumps({'scope': 'Original COMMAND_INT method; synthetic in-memory ACKs',
                                                   'fixtures': long_summary['fixtures'], 'cases': cases}, indent=2) + '\n')
print('verified', len(cases), 'synthetic COMMAND_INT ACK cases')
