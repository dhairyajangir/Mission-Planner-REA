"""Capture a hash-bound fallback inventory without loading the target assembly."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
name = sys.argv[1]
if Path(name).name != name or name in ('.', '..'):
    raise ValueError('expected a root-level assembly filename')
binary = root / 'mission-planner-portable' / name
base = root / 'mission-planner-binary-evidence/remaining-managed-members'
entry = next(row for row in json.loads((base / 'manifest.json').read_text())['results'] if row['path'] == name)
digest = hashlib.sha256(binary.read_bytes()).hexdigest()
if digest != entry['sha256']:
    raise ValueError('input does not match original REA inspection')
target = base / (Path(name).stem.lower().replace('.', '-') + '-cecil-methods.tsv.gz')
if target.exists():
    raise FileExistsError(target)
temporary = target.with_suffix('.tmp')
with subprocess.Popen([str(root / 'research-tools/CecilMethodInventory.exe'), str(binary)],
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
    with gzip.open(temporary, 'wb', compresslevel=6) as output:
        shutil.copyfileobj(proc.stdout, output)
    error = proc.stderr.read().decode('utf-8', errors='replace')
    if proc.wait() != 0:
        raise RuntimeError(error)
temporary.replace(target)
print(json.dumps({'assembly': name, 'sha256': digest, 'evidence': str(target),
                  'evidence_sha256': hashlib.sha256(target.read_bytes()).hexdigest()}))
