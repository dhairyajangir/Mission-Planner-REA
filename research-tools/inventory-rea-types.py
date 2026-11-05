"""Capture bounded REA member evidence for each top-level main-assembly type.

REA can exceed its representation budget on the whole executable.  Split each
failed batch recursively; retain failure records and never interpret them as
absence.  Re-running skips only previously validated complete batches.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
NODE = Path(r'C:\Users\think\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe')
CLI = ROOT / 'research-tools/node_modules/rea-agents/scripts/rea.mjs'
ASSEMBLY = ROOT / 'mission-planner-binary-evidence/_137'
NESTED = '--nested' in sys.argv[1:]
OUT = ROOT / ('mission-planner-binary-evidence/nested-type-batches' if NESTED else 'mission-planner-binary-evidence/type-batches')
OUT.mkdir(exist_ok=True)
inventory = json.loads((OUT.parent / 'rea-main-all-members.json').read_text(encoding='utf-8'))
types = inventory['normalized_result']['types']
names = (list(dict.fromkeys(t['name'] for t in types if t.get('enclosing_type_token') is not None))
         if NESTED else
         [t['full_name'] for t in types if t.get('enclosing_type_token') is None and t['name'] != '<Module>'])
assert hashlib.sha256(ASSEMBLY.read_bytes()).hexdigest() == inventory['subject']['digest']['sha256']
results = []

def inspect(group):
    ident = hashlib.sha256('\n'.join(group).encode()).hexdigest()[:16]
    dest = OUT / f'{ident}.json'
    tmp = OUT / f'{ident}.tmp'
    if dest.exists():
        data = json.loads(dest.read_text(encoding='utf-8'))
        n = data.get('normalized_result', {})
        if n.get('coverage', {}).get('state') == 'complete' and not n.get('selection', {}).get('unmatched_type_names'):
            results.append({'types': group, 'path': dest.name, 'status': 'complete', 'cached': True})
            return
    cmd = [str(NODE), str(CLI), 'inspect-managed-members', str(ASSEMBLY)]
    for name in group:
        cmd.extend(['--type', name])
    cmd.append('--json')
    with tmp.open('wb') as stream:
        p = subprocess.run(cmd, stdout=stream, stderr=subprocess.PIPE)
    try:
        data = json.loads(tmp.read_text(encoding='utf-8'))
        n = data.get('normalized_result', {})
        ok = p.returncode == 0 and n.get('coverage', {}).get('state') == 'complete' and not n.get('selection', {}).get('unmatched_type_names')
    except (ValueError, UnicodeError):
        ok = False
    if ok:
        tmp.replace(dest)
        results.append({'types': group, 'path': dest.name, 'status': 'complete'})
        print(f'complete {len(group)} types: {group[0]}', flush=True)
    elif len(group) > 1:
        tmp.replace(OUT / f'{ident}.partial.json')
        half = len(group) // 2
        inspect(group[:half])
        inspect(group[half:])
    else:
        tmp.replace(OUT / f'{ident}.partial.json')
        results.append({'types': group, 'path': f'{ident}.partial.json', 'status': 'partial',
                        'exit_code': p.returncode, 'stderr': p.stderr.decode(errors='replace')[:1000]})
        print(f'partial: {group[0]}', flush=True)
    (OUT / 'manifest.json').write_text(json.dumps({'assembly_sha256': inventory['subject']['digest']['sha256'],
                                                  'total_requested': len(names), 'batches': results}, indent=2), encoding='utf-8')

for i in range(0, len(names), 8):
    inspect(names[i:i+8])
print(f'finished: {len(names)} {"nested" if NESTED else "top-level"} type names requested', flush=True)
sys.exit(1 if any(r['status'] != 'complete' for r in results) else 0)
