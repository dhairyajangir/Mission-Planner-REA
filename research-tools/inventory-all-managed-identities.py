"""Inspect every managed-candidate PE from the portable inventory with REA."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from env_paths import NODE

root = Path(__file__).resolve().parent.parent
dist = root / 'mission-planner-portable'
evidence = root / 'mission-planner-binary-evidence'
node = str(NODE)
cli = root / 'research-tools/node_modules/rea-agents/scripts/rea.mjs'
inventory = json.loads((evidence / 'portable-binary-inventory.json').read_text(encoding='utf-8'))
files = [x for x in inventory['files'] if x['classification'] == 'managed-candidate']
out = evidence / 'all-managed-identities'
out.mkdir(exist_ok=True)

def inspect(row):
    path = dist / row['path']
    # Avoid using filenames as output paths; digest is stable and separators safe.
    ident = row['sha256'] + '-' + hashlib.sha256(row['path'].encode('utf-8')).hexdigest()[:12]
    target = out / (ident + '.json')
    if target.exists():
        try:
            d = json.loads(target.read_text(encoding='utf-8'))
            if d.get('subject', {}).get('digest', {}).get('sha256') == row['sha256']:
                return {'path': row['path'], 'sha256': row['sha256'], 'status': 'complete', 'evidence': target.name, 'cached': True}
        except (ValueError, UnicodeError):
            pass
    p = subprocess.run([node, str(cli), 'inspect-managed-artifact', str(path), '--json',
                        '--filter-output', 'subject,normalized_result.assembly,normalized_result.artifact,normalized_result.coverage,limitations'],
                       capture_output=True, timeout=90)
    try:
        d = json.loads(p.stdout)
        ok = (p.returncode == 0 and d.get('subject', {}).get('digest', {}).get('sha256') == row['sha256']
              and d.get('normalized_result', {}).get('coverage', {}).get('state') == 'complete')
    except (ValueError, UnicodeError):
        ok = False
    if ok:
        target.write_bytes(p.stdout)
    else:
        (out / (ident + '.failure.json')).write_bytes(p.stdout or p.stderr)
    return {'path': row['path'], 'sha256': row['sha256'], 'status': 'complete' if ok else 'failed',
            'evidence': target.name if ok else ident + '.failure.json', 'exit_code': p.returncode}

results = []
with ThreadPoolExecutor(max_workers=2) as pool:
    futures = [pool.submit(inspect, row) for row in files]
    for future in as_completed(futures):
        try:
            results.append(future.result())
        except Exception as exc:
            results.append({'status': 'failed', 'error': repr(exc)})
        (out / 'manifest.json').write_text(json.dumps({'requested': len(files), 'results': results}, indent=2) + '\n', encoding='utf-8')
        if len(results) % 20 == 0 or len(results) == len(files):
            print(f"{len(results)}/{len(files)} processed; {sum(x['status'] == 'failed' for x in results)} failed", flush=True)
sys.exit(1 if any(x['status'] != 'complete' for x in results) else 0)
