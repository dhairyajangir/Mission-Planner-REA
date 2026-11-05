"""Build multi-record playback fixtures from the prior captured heartbeat."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
source = root / 'sitl-evidence/tlog-playback-probe/control.tlog'
record = source.read_bytes()
if len(record) != 25 or record[8] != 0xfe:
    raise ValueError('unexpected control record')
bad = record[:-1] + bytes([record[-1] ^ 1])
fixtures = {'two-valid.tlog': record + record,
            'bad-then-valid.tlog': bad + record,
            'noise-before-frame.tlog': record[:8] + bytes([0x11, 0x22, 0x33]) + record[8:] + record,
            'noise-to-eof.tlog': record[:8] + bytes([0x11, 0x22, 0x33])}
out = root / 'sitl-evidence/tlog-recovery-probe'
out.mkdir(exist_ok=True)
manifest = {'source_sha256': hashlib.sha256(record).hexdigest(), 'files': {}}
for name, contents in fixtures.items():
    target = out / name
    if target.exists() and target.read_bytes() != contents:
        raise ValueError('existing fixture differs: ' + name)
    target.write_bytes(contents)
    manifest['files'][name] = {'size': len(contents), 'sha256': hashlib.sha256(contents).hexdigest()}
(out / 'fixtures.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
