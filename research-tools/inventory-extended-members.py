"""Capture additional REA managed-member inventories with resumable progress."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
node = r'C:\Users\think\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
cli = root / 'research-tools/node_modules/rea-agents/scripts/rea.mjs'
dist = root / 'mission-planner-portable'
out = root / 'mission-planner-binary-evidence/extended-assembly-members'
out.mkdir(exist_ok=True)
source = json.loads((root / 'mission-planner-binary-evidence/all-managed-identities/manifest.json').read_text())
known = {row['path']: row for row in source['results']}
files = ['plugins/AltitudeAngelWings.dll', 'plugins/AltitudeAngelWings.Plugin.dll', 'plugins/Bulb.dll',
         'plugins/FaceMap.dll', 'plugins/MavlinkMessagePlugin.dll', 'plugins/opendroneid.dll',
         'plugins/TerrainMakerPlugin.dll', 'plugins/TrackerHome.dll', 'Arduino.dll', 'DeviceProgramming.dll',
         'DroneCAN.dll', 'OSDConfigurator.dll', 'px4uploader.dll', 'WebCamService.dll', 'Updater.exe', 'version.exe']
manifest_path = out / 'manifest.json'
manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {'requested': files, 'results': []}
if manifest['requested'] != files:
    raise ValueError('inventory request changed')
done = {x['file']: x for x in manifest['results']}
for name in files:
    expected = known[name]['sha256']
    binary = dist / name
    if hashlib.sha256(binary.read_bytes()).hexdigest() != expected:
        raise ValueError('input digest changed: ' + name)
    if name in done:
        continue
    target = out / (name.replace('/', '__') + '.json')
    temp = target.with_suffix('.json.tmp')
    try:
        with temp.open('wb') as stream:
            p = subprocess.run([node, str(cli), 'inspect-managed-members', str(binary), '--json'],
                               stdout=stream, stderr=subprocess.PIPE, timeout=240)
        data = json.loads(temp.read_text(encoding='utf-8'))
        normalized = data.get('normalized_result', {})
        digest = (data.get('subject') or {}).get('digest', {}).get('sha256')
        row = {'file': name, 'exit_code': p.returncode, 'sha256': digest,
               'coverage': normalized.get('coverage'), 'types': len(normalized.get('types', [])),
               'methods': len(normalized.get('methods', [])), 'call_edges': len(normalized.get('call_edges', [])),
               'evidence': target.name, 'digest_matches': digest == expected}
        temp.replace(target)
    except Exception as exc:
        row = {'file': name, 'error': repr(exc), 'evidence': temp.name, 'digest_matches': False}
    manifest['results'].append(row)
    temp_manifest = manifest_path.with_suffix('.json.tmp')
    temp_manifest.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    temp_manifest.replace(manifest_path)
    print(f"{len(manifest['results'])}/{len(files)} {name}: {(row.get('coverage') or {}).get('state', row.get('error', 'unknown'))}", flush=True)
if any(x.get('exit_code') != 0 or not x.get('digest_matches') or
       (x.get('coverage') or {}).get('state') != 'complete' for x in manifest['results']):
    sys.exit(1)
