"""Capture REA assembly references for each inventoried managed PE.

Reference declarations are not evidence of successful runtime binding. The
per-file output is hash-bound and the manifest is resumable after interruption.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from env_paths import NODE

root = Path(__file__).resolve().parent.parent
dist = root / 'mission-planner-portable'
evidence = root / 'mission-planner-binary-evidence'
node = NODE
cli = root / 'research-tools/node_modules/rea-agents/scripts/rea.mjs'
inventory = json.loads((evidence / 'portable-binary-inventory.json').read_text(encoding='utf-8'))
files = [row for row in inventory['files'] if row['classification'] == 'managed-candidate']
out = evidence / 'managed-references'
out.mkdir(exist_ok=True)
manifest_path = out / 'manifest.json'
rows = []

def save():
    temp = out / 'manifest.tmp'
    temp.write_text(json.dumps({'requested': len(files), 'results': rows}, indent=2) + '\n', encoding='utf-8')
    temp.replace(manifest_path)

for entry in files:
    ident = entry['sha256'] + '-' + hashlib.sha256(entry['path'].encode()).hexdigest()[:12]
    target = out / (ident + '.json')
    cached = False
    if target.exists():
        try:
            prior = json.loads(target.read_text(encoding='utf-8'))
            cached = (prior.get('subject', {}).get('digest', {}).get('sha256') == entry['sha256'] and
                      prior.get('normalized_result', {}).get('coverage', {}).get('state') == 'complete' and
                      isinstance(prior.get('normalized_result', {}).get('references'), list))
        except (ValueError, UnicodeError):
            pass
    row = {'path': entry['path'], 'sha256': entry['sha256'], 'evidence': target.name}
    if cached:
        row.update(status='complete', cached=True)
    else:
        try:
            proc = subprocess.run([str(node), str(cli), 'inspect-managed-artifact', str(dist / entry['path']), '--json',
                                   '--filter-output', 'subject,normalized_result.assembly,normalized_result.references,normalized_result.coverage,limitations'],
                                  capture_output=True, timeout=120)
            data = json.loads(proc.stdout)
            valid = (proc.returncode == 0 and data.get('subject', {}).get('digest', {}).get('sha256') == entry['sha256'] and
                     data.get('normalized_result', {}).get('coverage', {}).get('state') == 'complete' and
                     isinstance(data.get('normalized_result', {}).get('references'), list))
            if valid:
                target.write_bytes(proc.stdout)
            else:
                (out / (ident + '.failure.json')).write_bytes(proc.stdout or proc.stderr)
            row.update(status='complete' if valid else 'failed', exit_code=proc.returncode)
        except Exception as exc:
            row.update(status='failed', error=repr(exc))
    rows.append(row)
    save()
    if len(rows) % 10 == 0 or len(rows) == len(files):
        print(f"{len(rows)}/{len(files)} inspected; {sum(r['status'] != 'complete' for r in rows)} failed", flush=True)
sys.exit(1 if any(row['status'] != 'complete' for row in rows) else 0)
