"""Capture REA export-table evidence for non-CLI PE candidates in the ZIP."""
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
files = [x for x in inventory['files'] if x['classification'] == 'native-or-other-pe']
out = evidence / 'native-exports'
out.mkdir(exist_ok=True)

def inspect(row):
    ident = row['sha256'] + '-' + hashlib.sha256(row['path'].encode()).hexdigest()[:12]
    target = out / (ident + '.json')
    p = subprocess.run([node, str(cli), 'inspect-native-exports', str(dist / row['path']), '--json'],
                       capture_output=True, timeout=90)
    try:
        d = json.loads(p.stdout)
        n = d.get('normalized_result', {})
        ok = (p.returncode == 0 and d.get('subject', {}).get('digest', {}).get('sha256') == row['sha256']
              and n.get('coverage', {}).get('status') == 'complete')
    except (ValueError, UnicodeError):
        ok = False
    target.write_bytes(p.stdout or p.stderr)
    return {'path': row['path'], 'sha256': row['sha256'], 'status': 'complete' if ok else 'failed',
            'evidence': target.name, 'exit_code': p.returncode}

results = []
with ThreadPoolExecutor(max_workers=2) as pool:
    futures = [pool.submit(inspect, row) for row in files]
    for future in as_completed(futures):
        try:
            results.append(future.result())
        except Exception as exc:
            results.append({'status': 'failed', 'error': repr(exc)})
        (out / 'manifest.json').write_text(json.dumps({'requested': len(files), 'results': results}, indent=2) + '\n', encoding='utf-8')
        if len(results) % 10 == 0 or len(results) == len(files):
            print(f"{len(results)}/{len(files)} processed; {sum(x['status'] == 'failed' for x in results)} failed", flush=True)
sys.exit(1 if any(x['status'] != 'complete' for x in results) else 0)
