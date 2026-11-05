"""Construct timestamped and raw heartbeat sequences from local fixture bytes."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
control = (root / 'sitl-evidence/tlog-playback-probe/control.tlog').read_bytes()
if len(control) != 25 or control[8] != 0xfe:
    raise ValueError('unexpected heartbeat fixture')
frame = control[8:]
first = 1600000000123456
second = first + 1_001_234
fixtures = {'timestamped.tlog': first.to_bytes(8, 'big') + frame + second.to_bytes(8, 'big') + frame,
            'backward.tlog': second.to_bytes(8, 'big') + frame + first.to_bytes(8, 'big') + frame,
            'raw.rlog': frame + frame,
            'raw.tlog': frame + frame}
out = root / 'sitl-evidence/tlog-timestamp-probe'
out.mkdir(exist_ok=True)
manifest = {'control_sha256': hashlib.sha256(control).hexdigest(), 'timestamp_us': [first, second], 'files': {}}
for name, contents in fixtures.items():
    path = out / name
    if path.exists() and path.read_bytes() != contents:
        raise ValueError('fixture changed: ' + name)
    path.write_bytes(contents)
    manifest['files'][name] = {'size': len(contents), 'sha256': hashlib.sha256(contents).hexdigest()}
(out / 'fixtures.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
