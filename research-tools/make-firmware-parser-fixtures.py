"""Create synthetic APJ-shaped JSON files, never usable as real firmware."""
import base64
import hashlib
import json
from pathlib import Path
import zlib

run = Path(__file__).resolve().parent.parent / 'sitl-evidence/firmware-parser-probe'
run.mkdir(exist_ok=True)
if (run / 'fixtures.json').exists():
    raise FileExistsError('refusing to overwrite fixtures')
cases = [('exact-4.apj', 4, b'ABCD'), ('short-image.apj', 8, b'ABCD'),
         ('exact-3.apj', 3, b'ABC'), ('exact-5.apj', 5, b'ABCDE'),
         ('exact-7.apj', 7, b'ABCDEFG')]
manifest = []
for name, declared, raw in cases:
    payload = {'board_id': 9999, 'image_size': declared,
               'image': base64.b64encode(zlib.compress(raw)).decode('ascii'),
               'description': 'Synthetic parser test; not firmware'}
    path = run / name
    path.write_text(json.dumps(payload) + '\n', encoding='ascii')
    manifest.append({'file': name, 'declared': declared, 'decompressed_hex': raw.hex(),
                     'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
(run / 'fixtures.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
