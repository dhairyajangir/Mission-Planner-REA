"""Capture REA P/Invoke boundary evidence for the portable managed candidates."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parent.parent
dist = (root / 'mission-planner-portable').resolve()
inventory = root / 'mission-planner-binary-evidence/all-managed-identities/manifest.json'
inputs = json.loads(inventory.read_text())['results']
out = root / 'mission-planner-binary-evidence/managed-native-all'
out.mkdir(exist_ok=True)
manifest_file = out / 'manifest.json'
manifest = json.loads(manifest_file.read_text()) if manifest_file.exists() else {
    'input_sha256': hashlib.sha256(inventory.read_bytes()).hexdigest(), 'requested': len(inputs), 'results': []}
if manifest['input_sha256'] != hashlib.sha256(inventory.read_bytes()).hexdigest(): raise ValueError('inventory changed')
done = {x['path'] for x in manifest['results']}
node = r'C:\Users\think\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
cli = root / 'research-tools/node_modules/rea-agents/scripts/rea.mjs'
for entry in inputs:
    relative = entry['path']
    if relative in done: continue
    if shutil.disk_usage(root).free < 4 * 1024**3: raise RuntimeError('less than 4 GiB free')
    binary = (dist / relative).resolve()
    binary.relative_to(dist)
    sha = hashlib.sha256(binary.read_bytes()).hexdigest()
    if sha != entry['sha256']: raise ValueError('subject changed: ' + relative)
    key = hashlib.sha256(relative.encode()).hexdigest()[:16]
    row = {'path': relative, 'sha256': sha}
    try:
        proc = subprocess.run([node, str(cli), 'inspect-managed-native-boundaries', str(binary), '--json'],
                              capture_output=True, timeout=180)
        data = json.loads(proc.stdout)
        if data['subject']['digest']['sha256'] != sha: raise ValueError('subject digest mismatch')
        payload = proc.stdout
        name = key + '.json.gz'
        with gzip.open(out / name, 'wb', compresslevel=6) as file: file.write(payload)
        row.update(exit_code=proc.returncode, coverage=data['normalized_result']['coverage'],
                   evidence=name, evidence_sha256=hashlib.sha256((out / name).read_bytes()).hexdigest())
    except Exception as exc:
        row['error'] = repr(exc)
    manifest['results'].append(row)
    tmp = manifest_file.with_suffix('.tmp')
    tmp.write_text(json.dumps(manifest, indent=2) + '\n')
    tmp.replace(manifest_file)
    print(f"{len(manifest['results'])}/{len(inputs)} {relative}: {row.get('coverage', row.get('error'))}", flush=True)
print('finished', flush=True)
