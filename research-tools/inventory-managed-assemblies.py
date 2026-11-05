"""Use REA to inventory selected first-party and MAVLink managed PE files."""
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
node = r'C:\Users\think\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
cli = root / 'research-tools/node_modules/rea-agents/scripts/rea.mjs'
dist = root / 'mission-planner-portable'
out = root / 'mission-planner-binary-evidence/assemblies'
out.mkdir(exist_ok=True)
files = sorted(dist.glob('MissionPlanner.*.dll')) + [dist / 'MAVLink.dll']
files += sorted((dist / 'plugins').glob('MissionPlanner.*.dll'))
rows = []
for f in files:
    name = f.relative_to(dist).as_posix().replace('/', '__')
    target = out / (name + '.json')
    with target.open('wb') as stream:
        p = subprocess.run([node, str(cli), 'inspect-managed-artifact', str(f), '--json'],
                           stdout=stream, stderr=subprocess.PIPE)
    try:
        evidence = json.loads(target.read_text(encoding='utf-8'))
        norm = evidence.get('normalized_result', {})
        row = {'file': f.relative_to(dist).as_posix(), 'exit_code': p.returncode,
               'sha256': evidence.get('subject', {}).get('digest', {}).get('sha256'),
               'assembly': norm.get('assembly'), 'coverage': norm.get('coverage'),
               'evidence': target.name}
    except (ValueError, UnicodeError):
        row = {'file': f.relative_to(dist).as_posix(), 'exit_code': p.returncode,
               'stderr': p.stderr.decode(errors='replace')[:500], 'evidence': target.name}
    rows.append(row)
    (out / 'manifest.json').write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')
    print(f"{row['exit_code']} {row['file']}", flush=True)
print(f'inspected {len(rows)} files', flush=True)
sys.exit(1 if any(r['exit_code'] != 0 for r in rows) else 0)
