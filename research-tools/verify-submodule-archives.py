"""Check additional submodule ZIP entries against pinned upstream Git blob IDs."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

base = Path(__file__).resolve().parent / 'submodule-archives'
names = sys.argv[1:]
results = []
for name in names:
    tree = json.loads((base / f'{name}-tree.json').read_text(encoding='utf-8'))
    if tree['truncated']:
        raise ValueError(f'truncated tree: {name}')
    blobs = {x['path']: x['sha'] for x in tree['tree'] if x['type'] == 'blob'}
    found = {}
    with zipfile.ZipFile(base / f'{name}.zip') as z:
        if z.comment.decode('ascii') != tree['sha']:
            raise ValueError(f'ZIP/tree commit mismatch: {name}')
        roots = {x.filename.split('/')[0] for x in z.infolist()}
        if len(roots) != 1:
            raise ValueError(f'non-unique archive root: {name}')
        prefix = next(iter(roots)) + '/'
        for f in z.infolist():
            if f.is_dir():
                continue
            path = f.filename.removeprefix(prefix)
            if path == f.filename or path in found:
                raise ValueError(f'unexpected or duplicate path: {f.filename}')
            digest = hashlib.sha1(f'blob {f.file_size}\0'.encode())
            with z.open(f) as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            found[path] = digest.hexdigest()
    mismatch = [path for path in set(found) & set(blobs) if found[path] != blobs[path]]
    missing = sorted(set(blobs) - set(found))
    extra = sorted(set(found) - set(blobs))
    row = {'name': name, 'commit': tree['sha'], 'zip_files': len(found), 'git_blobs': len(blobs),
           'mismatches': mismatch, 'missing': missing, 'extra': extra,
           'nested_gitlinks': [{'path': x['path'], 'sha': x['sha']} for x in tree['tree'] if x['type'] == 'commit']}
    results.append(row)
    print(f'{name}: {len(found)} files; mismatches={len(mismatch)} missing={len(missing)} extra={len(extra)}', flush=True)
    (base / 'additional-verification.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    if mismatch or missing or extra:
        raise ValueError(f'ZIP verification failed: {name}')
(base / 'additional-verification.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
