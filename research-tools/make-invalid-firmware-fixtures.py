"""Generate malformed, synthetic APJ-shaped parser inputs for local tests."""
import base64
import hashlib
import json
from pathlib import Path
import zlib

run = Path(__file__).resolve().parent.parent / 'sitl-evidence/firmware-parser-invalid'
run.mkdir(exist_ok=True)
if (run / 'fixtures.json').exists():
    raise FileExistsError('refusing to overwrite fixtures')
compressed = zlib.compress(b'ABCD')
cases = [('invalid-base64.apj', 4, '%%%'),
         ('invalid-zlib.apj', 4, base64.b64encode(b'not-zlib').decode('ascii')),
         ('truncated-zlib.apj', 4, base64.b64encode(compressed[:4]).decode('ascii')),
         ('zero-size.apj', 0, base64.b64encode(compressed).decode('ascii'))]
manifest = []
for name, size, image in cases:
    payload = {'board_id': 9999, 'image_size': size, 'image': image,
               'description': 'Synthetic parser test; not firmware'}
    path = run / name
    path.write_text(json.dumps(payload) + '\n', encoding='ascii')
    try:
        raw = zlib.decompress(base64.b64decode(image, validate=True))
        independent = {'status': 'ok', 'data_hex': raw.hex()}
    except Exception as exc:
        independent = {'status': 'error', 'type': type(exc).__name__}
    manifest.append({'file': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                     'independent': independent})
(run / 'fixtures.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
