"""Recover REA member evidence in bounded batches for Accord.Statistics.

Type names come from independent Cecil metadata. Nested bare names are REA's
selection convention, so collisions may select multiple nested types. Evidence
must later be compared by metadata token, not just by number of queries.
"""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from env_paths import NODE

root = Path(__file__).resolve().parent.parent
base = root / 'mission-planner-binary-evidence/remaining-managed-members'
relative = sys.argv[1] if len(sys.argv) > 1 else 'Accord.Statistics.dll'
if Path(relative).name != relative or relative in ('.', '..'):
    raise ValueError('expected a root-level assembly filename')
slug = Path(relative).stem.lower().replace('.', '-')
out = root / 'mission-planner-binary-evidence' / (slug + '-batches')
out.mkdir(exist_ok=True)
node = str(NODE)
cli = root / 'research-tools/node_modules/rea-agents/scripts/rea.mjs'
binary = root / 'mission-planner-portable' / relative
digest = hashlib.sha256(binary.read_bytes()).hexdigest()
original = json.loads((base / 'manifest.json').read_text())
entry = next(x for x in original['results'] if x['path'] == relative)
if digest != entry['sha256']:
    raise ValueError('assembly hash differs from original inventory')
rows = [line.split('\t') for line in (base / (slug + '-cecil-types.tsv')).read_text(encoding='utf-8').splitlines()]
names = list(dict.fromkeys((row[1] if row[3] == 'top' else row[2]) for row in rows if row[2] != '<Module>'))
manifest_path = out / 'manifest.json'
manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
    'assembly_sha256': digest, 'requested_names': names, 'batches': []}
if manifest['assembly_sha256'] != digest or manifest['requested_names'] != names:
    raise ValueError('type inventory changed')
done = {tuple(row['names']) for row in manifest['batches'] if row['status'] == 'complete'}


def record(row):
    manifest['batches'].append(row)
    temp = manifest_path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(manifest, indent=2) + '\n')
    temp.replace(manifest_path)


def inspect(group):
    if tuple(group) in done:
        return
    if shutil.disk_usage(root).free < 4 * 1024 ** 3:
        raise RuntimeError('less than 4 GiB free')
    tag = hashlib.sha256('\n'.join(group).encode()).hexdigest()[:16]
    tmp = out / (tag + '.tmp.json')
    cmd = [node, str(cli), 'inspect-managed-members', str(binary)]
    for name in group:
        cmd.extend(['--type', name])
    cmd.append('--json')
    try:
        with tmp.open('wb') as stream:
            proc = subprocess.run(cmd, stdout=stream, stderr=subprocess.PIPE, timeout=240)
        data = json.loads(tmp.read_text(encoding='utf-8'))
        n = data.get('normalized_result', {})
        ok = (proc.returncode == 0 and data['subject']['digest']['sha256'] == digest and
              n.get('coverage', {}).get('state') == 'complete' and
              not n.get('selection', {}).get('unmatched_type_names'))
        reason = n.get('coverage', {})
    except Exception as exc:
        ok, reason = False, {'exception': repr(exc)}
    if ok:
        name = tag + '.json.gz'
        with tmp.open('rb') as src, gzip.open(out / name, 'wb', compresslevel=6) as dst:
            shutil.copyfileobj(src, dst)
        tmp.unlink()
        record({'names': group, 'status': 'complete', 'evidence': name,
                'types': len(n.get('types', [])), 'methods': len(n.get('methods', []))})
        print(f'complete batch of {len(group)}: {group[0]}', flush=True)
    elif len(group) > 1:
        if tmp.exists():
            tmp.unlink()
        middle = len(group) // 2
        inspect(group[:middle])
        inspect(group[middle:])
    else:
        if tmp.exists():
            tmp.rename(out / (tag + '.partial.json'))
        record({'names': group, 'status': 'partial', 'reason': reason})
        print('partial ' + group[0], flush=True)


for i in range(0, len(names), 8):
    inspect(names[i:i+8])
print(f'finished {len(names)} type-name queries', flush=True)
sys.exit(1 if any(x['status'] != 'complete' for x in manifest['batches']) else 0)
