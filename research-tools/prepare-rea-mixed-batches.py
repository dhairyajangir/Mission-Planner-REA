"""Build a separate batch set from original REA and identified raised-budget captures."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
assembly = sys.argv[1]
if Path(assembly).name != assembly: raise ValueError('invalid assembly')
slug = Path(assembly).stem.lower().replace('.', '-')
base = root / 'mission-planner-binary-evidence'
original = base / (slug + '-batches')
target = base / (slug + '-mixed-batches')
raised = base / 'rea-raised-budget'
manifest = json.loads((original / 'manifest.json').read_text())
if target.exists(): raise FileExistsError(target)
target.mkdir()
new_batches = []
for batch in manifest['batches']:
    row = dict(batch)
    if row['status'] == 'complete':
        shutil.copyfile(original / row['evidence'], target / row['evidence'])
        row['tool_variant'] = 'original'
    else:
        if len(row['names']) != 1: raise ValueError('partial group must have one name')
        selection = row['names'][0]
        stem = slug + '-' + selection.lower().replace('.', '-')
        recovered = raised / (stem + '.json.gz')
        recovered_summary = json.loads((raised / (stem + '-summary.json')).read_text())
        if recovered_summary['process_exit'] != 0 or recovered_summary['coverage']['state'] != 'complete':
            raise ValueError('raised-budget selection incomplete')
        if hashlib.sha256(recovered.read_bytes()).hexdigest() != recovered_summary['capture_sha256']:
            raise ValueError('raised-budget capture hash mismatch')
        name = 'raised-' + recovered.name
        shutil.copyfile(recovered, target / name)
        row = {'names': [selection], 'status': 'complete', 'evidence': name, 'tool_variant': 'raised-budget',
               'types': recovered_summary['types'], 'methods': recovered_summary['methods']}
    new_batches.append(row)
manifest['batches'] = new_batches
manifest['source_manifest_sha256'] = hashlib.sha256((original / 'manifest.json').read_bytes()).hexdigest()
manifest['modification_sha256'] = hashlib.sha256((base / 'rea-raised-budget-modification.json').read_bytes()).hexdigest()
(target / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(assembly, len(new_batches), 'batches prepared')
