import base64
import hashlib
import json
from pathlib import Path
import zlib

run = Path(__file__).resolve().parent.parent / 'sitl-evidence/mock-uploader-probe'
run.mkdir(exist_ok=True)
if (run / 'fixtures.json').exists():
    raise FileExistsError('refusing to overwrite prior fixtures')
manifest = []
for name, raw in [('complete.apj', b'A' * 252), ('short.apj', b'A' * 248)]:
    payload = {'board_id': 9999, 'image_size': 252, 'image': base64.b64encode(zlib.compress(raw)).decode('ascii'),
               'description': 'Synthetic mock uploader test; not firmware'}
    path = run / name
    path.write_text(json.dumps(payload) + '\n', encoding='ascii')
    manifest.append({'file': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                     'declared': 252, 'actual': len(raw), 'decompressed_sha256': hashlib.sha256(raw).hexdigest()})
(run / 'fixtures.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
