"""Capture independent type metadata for a root-level managed assembly."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
name = sys.argv[1]
if Path(name).name != name or name in ('.', '..'):
    raise ValueError('expected a root-level assembly filename')
binary = root / 'mission-planner-portable' / name
base = root / 'mission-planner-binary-evidence/remaining-managed-members'
manifest = json.loads((base / 'manifest.json').read_text())
entry = next(row for row in manifest['results'] if row['path'] == name)
if hashlib.sha256(binary.read_bytes()).hexdigest() != entry['sha256']:
    raise ValueError('input does not match the REA subject')
result = subprocess.run([str(root / 'research-tools/CecilTypeInventory.exe'), str(binary)],
                        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
rows = result.stdout.decode('utf-8').splitlines()
if not rows or any(len(row.split('\t')) != 5 for row in rows):
    raise ValueError('unexpected Cecil output')
target = base / (Path(name).stem.lower().replace('.', '-') + '-cecil-types.tsv')
if target.exists() and target.read_bytes() != result.stdout:
    raise ValueError('existing inventory differs; preserving it')
target.write_bytes(result.stdout)
print(f'{name}: {len(rows)} type records saved to {target}')
