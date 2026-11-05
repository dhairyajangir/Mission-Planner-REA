"""Retrieve GitHub ZIP export-ignored lwIP files and validate their Git blobs."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

root = Path(__file__).resolve().parent / 'submodule-archives'
tree = json.loads((root / 'lwip-tree.json').read_text(encoding='utf-8'))
if tree['truncated']:
    raise ValueError('truncated upstream tree')
blobs = {x['path']: x['sha'] for x in tree['tree'] if x['type'] == 'blob'}
with zipfile.ZipFile(root / 'lwip.zip') as z:
    if z.comment.decode() != tree['sha']:
        raise ValueError('ZIP commit mismatch')
    files = {x.filename.split('/', 1)[1] for x in z.infolist() if not x.is_dir()}
missing = sorted(set(blobs) - files)
out = root / 'lwip-export-ignored'
out.mkdir(exist_ok=True)
for rel in missing:
    dest = (out / rel).resolve()
    if not dest.is_relative_to(out.resolve()):
        raise ValueError(f'unsafe path {rel}')
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f'https://raw.githubusercontent.com/ArduPilot/lwip/{tree["sha"]}/{rel}'
    subprocess.run(['curl.exe', '-fsSL', '-o', str(dest), url], check=True)
    data = dest.read_bytes()
    actual = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
    if actual != blobs[rel]:
        raise ValueError(f'blob mismatch: {rel}')
    print(f'verified {rel}', flush=True)
(root / 'lwip-export-ignored.json').write_text(json.dumps({'commit': tree['sha'], 'files': missing}, indent=2) + '\n')
