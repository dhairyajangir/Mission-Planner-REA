"""Capture REA managed-to-native boundary evidence for two core binaries."""
import hashlib
import json
from pathlib import Path
import subprocess
from env_paths import NODE

root = Path(__file__).resolve().parent.parent
node = NODE
cli = root / 'research-tools/node_modules/rea-agents/scripts/rea.mjs'
dist = root / 'mission-planner-portable'
output = root / 'mission-planner-binary-evidence/managed-native-boundaries'
output.mkdir(exist_ok=True)
manifest = []
for name in ('MissionPlanner.exe', 'MissionPlanner.Utilities.dll'):
    binary = dist / name
    sha = hashlib.sha256(binary.read_bytes()).hexdigest()
    path = output / (name + '.json')
    if path.exists():
        raise FileExistsError(f'refusing to overwrite {path}')
    proc = subprocess.run([str(node), str(cli), 'inspect-managed-native-boundaries', str(binary), '--json'],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    path.write_bytes(proc.stdout or proc.stderr)
    try:
        data = json.loads(proc.stdout)
        match = data.get('subject', {}).get('digest', {}).get('sha256') == sha
        coverage = data.get('normalized_result', {}).get('coverage', {}).get('state')
    except ValueError:
        match, coverage = False, None
    manifest.append({'file': name, 'sha256': sha, 'output': path.name, 'exit_code': proc.returncode,
                     'digest_matches': match, 'coverage': coverage})
(output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
if any(entry['exit_code'] != 0 or not entry['digest_matches'] for entry in manifest):
    raise SystemExit(1)
