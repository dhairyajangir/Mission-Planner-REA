"""Capture member-level REA evidence for each inventoried supporting assembly."""
import json
from pathlib import Path
import subprocess
import sys
from env_paths import NODE

root = Path(__file__).resolve().parent.parent
node = str(NODE)
cli = root / 'research-tools/node_modules/rea-agents/scripts/rea.mjs'
dist = root / 'mission-planner-portable'
out = root / 'mission-planner-binary-evidence/assembly-members'
out.mkdir(exist_ok=True)
files = json.loads((root / 'mission-planner-binary-evidence/assemblies/manifest.json').read_text(encoding='utf-8'))
rows = []
for entry in files:
    f = dist / entry['file']
    name = entry['file'].replace('/', '__') + '.json'
    target = out / name
    with target.open('wb') as stream:
        p = subprocess.run([node, str(cli), 'inspect-managed-members', str(f), '--json'],
                           stdout=stream, stderr=subprocess.PIPE)
    try:
        data = json.loads(target.read_text(encoding='utf-8'))
        n = data.get('normalized_result', {})
        row = {'file': entry['file'], 'exit_code': p.returncode,
               'sha256': (data.get('subject') or {}).get('digest', {}).get('sha256'),
               'coverage': n.get('coverage'), 'types': len(n.get('types', [])),
               'methods': len(n.get('methods', [])), 'call_edges': len(n.get('call_edges', [])),
               'evidence': name}
        if row['sha256'] != entry['sha256']:
            row['hash_mismatch'] = True
    except (ValueError, UnicodeError):
        row = {'file': entry['file'], 'exit_code': p.returncode,
               'stderr': p.stderr.decode(errors='replace')[:500], 'evidence': name}
    rows.append(row)
    (out / 'manifest.json').write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')
    print(f"{row['file']}: {(row.get('coverage') or {}).get('state', 'error')}", flush=True)
print(f'finished {len(rows)} assemblies', flush=True)
sys.exit(1 if any(r['exit_code'] != 0 or r.get('hash_mismatch') or
                  (r.get('coverage') or {}).get('state') != 'complete' for r in rows) else 0)
