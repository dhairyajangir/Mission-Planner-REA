"""Check the progress-only fixture and parse the two method outcomes."""
import hashlib
import json
from pathlib import Path
import re
root = Path(__file__).resolve().parent.parent
out = root / 'sitl-evidence/command-progress-only'
fixture = json.loads((out / 'fixture.json').read_text())
data = (out / 'in-progress-only.bin').read_bytes()
source = (root / 'sitl-evidence/command-ack-synthetic/in-progress.bin').read_bytes()
decoded = json.loads((root / 'sitl-evidence/command-ack-synthetic/summary.json').read_text())
assert hashlib.sha256(source).hexdigest() == fixture['source_sha256']
assert hashlib.sha256(data).hexdigest() == fixture['sha256'] and data == source[:11]
assert decoded['cases']['in-progress']['frames'][0] == [1, 1, 510, 5]
text = (out / 'probe.log').read_text(encoding='utf-16')
patterns = {'long': r'FORM=long TIMEOUT=Timeout on read - doCommand REMAINING=0 GIVE=False ELAPSED_MS=(\d+)',
            'int': r'FORM=int RESULT=False REMAINING=0 GIVE=False ELAPSED_MS=(\d+)'}
observed = {}
for name, pattern in patterns.items():
    match = re.search(pattern, text)
    assert match
    observed[name] = {'line': match.group(0), 'elapsed_ms': int(match.group(1))}
summary = {'scope': 'Original command methods, synthetic in-memory IN_PROGRESS ACK without terminal ACK',
           'fixture': fixture, 'decoded_ack': [1, 1, 510, 5], 'observed': observed}
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(observed))
