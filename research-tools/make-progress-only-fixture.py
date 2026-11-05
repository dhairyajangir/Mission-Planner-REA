"""Copy the previously verified first in-progress ACK into a new fixture."""
import hashlib
import json
from pathlib import Path
root = Path(__file__).resolve().parent.parent
source = root / 'sitl-evidence/command-ack-synthetic/in-progress.bin'
out = root / 'sitl-evidence/command-progress-only'
out.mkdir(exist_ok=False)
data = source.read_bytes()
if len(data) != 22: raise ValueError('unexpected source fixture length')
first = data[:11]
(out / 'in-progress-only.bin').write_bytes(first)
(out / 'fixture.json').write_text(json.dumps({'source_sha256': hashlib.sha256(data).hexdigest(),
    'sha256': hashlib.sha256(first).hexdigest(), 'size': len(first)}, indent=2) + '\n')
print('saved one ACK', hashlib.sha256(first).hexdigest())
