"""Resumable REA member inventory for remaining portable managed assemblies.

Raw results are gzip-compressed to limit disk use. Existing main and support
inventories are left untouched. A per-file failure remains explicit.
"""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
from env_paths import NODE

root = Path(__file__).resolve().parent.parent
evidence = root / 'mission-planner-binary-evidence'
dist = root / 'mission-planner-portable'
node = str(NODE)
cli = root / 'research-tools/node_modules/rea-agents/scripts/rea.mjs'
out = evidence / 'remaining-managed-members'
out.mkdir(exist_ok=True)
all_rows = json.loads((evidence / 'all-managed-identities/manifest.json').read_text())['results']
already = {x['file'] for x in json.loads((evidence / 'assembly-members/manifest.json').read_text())}
already.update(x['file'] for x in json.loads((evidence / 'extended-assembly-members/manifest.json').read_text())['results'])
already.add('MissionPlanner.exe')
requested = [x for x in all_rows if x['path'] not in already]
manifest_path = out / 'manifest.json'
manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
    'requested_paths': [x['path'] for x in requested], 'results': []}
if manifest['requested_paths'] != [x['path'] for x in requested]:
    raise ValueError('inventory inputs changed')
completed = {row['path'] for row in manifest['results']}
for entry in requested:
    name = entry['path']
    if name in completed:
        continue
    if shutil.disk_usage(root).free < 4 * 1024 ** 3:
        print('STOP: less than 4 GiB free; existing evidence preserved', flush=True)
        sys.exit(2)
    binary = dist / name
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    if digest != entry['sha256']:
        raise ValueError('input digest changed: ' + name)
    tag = hashlib.sha256(name.encode('utf-8')).hexdigest()[:12]
    evidence_name = digest + '-' + tag + '.json.gz'
    temp = out / (evidence_name + '.tmp.json')
    compressed_temp = out / (evidence_name + '.tmp')
    try:
        with temp.open('wb') as stream:
            proc = subprocess.run([node, str(cli), 'inspect-managed-members', str(binary), '--json'],
                                  stdout=stream, stderr=subprocess.PIPE, timeout=300)
        data = json.loads(temp.read_text(encoding='utf-8'))
        normalized = data.get('normalized_result', {})
        subject_hash = (data.get('subject') or {}).get('digest', {}).get('sha256')
        row = {'path': name, 'sha256': digest, 'exit_code': proc.returncode, 'subject_matches': subject_hash == digest,
               'coverage': normalized.get('coverage'), 'types': len(normalized.get('types', [])),
               'methods': len(normalized.get('methods', [])), 'call_edges': len(normalized.get('call_edges', [])),
               'evidence': evidence_name}
        with temp.open('rb') as src, gzip.open(compressed_temp, 'wb', compresslevel=6) as dst:
            shutil.copyfileobj(src, dst)
        compressed_temp.replace(out / evidence_name)
        temp.unlink()
    except Exception as exc:
        row = {'path': name, 'sha256': digest, 'error': repr(exc), 'traceback': traceback.format_exc(),
               'partial_output': temp.name if temp.exists() else None}
    manifest['results'].append(row)
    staged = manifest_path.with_suffix('.json.tmp')
    staged.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    staged.replace(manifest_path)
    print(f"{len(manifest['results'])}/{len(requested)} {name}: "
          f"{(row.get('coverage') or {}).get('state', row.get('error', 'unknown'))}", flush=True)
failed = [row for row in manifest['results'] if row.get('exit_code') != 0 or not row.get('subject_matches') or
          (row.get('coverage') or {}).get('state') != 'complete']
print(f'finished {len(manifest["results"])}; non-complete {len(failed)}', flush=True)
sys.exit(1 if failed else 0)
