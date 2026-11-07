"""Run REA ELF-note and export-table inspections on source-built variants."""
import hashlib
import json
from pathlib import Path
import subprocess
from env_paths import NODE

root = Path(__file__).resolve().parent.parent
node = NODE
cli = root / 'research-tools/node_modules/rea-agents/scripts/rea.mjs'
folder = root / 'sitl-evidence/archive-built-variants'
manifest = folder / 'rea-variant-manifest.json'
entries = json.loads(manifest.read_text()) if manifest.exists() else []
for name in ('arduplane', 'ardurover', 'ardusub', 'blimp', 'antennatracker'):
    binary = folder / name
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    for command in ('inspect-elf-notes', 'inspect-native-exports'):
        existing = [x for x in entries if x['binary'] == name and x['operation'] == command]
        if existing:
            if len(existing) != 1 or existing[0]['sha256'] != digest or not (folder / existing[0]['output']).exists():
                raise RuntimeError(f'existing evidence mismatch: {name} {command}')
            continue
        args = [str(node), str(cli), command, str(binary)]
        if command == 'inspect-elf-notes':
            args += ['--max-entries', '256']
        args += ['--json']
        proc = subprocess.run(args, capture_output=True, timeout=120)
        out = folder / f'{name}-{command}.json'
        out.write_bytes(proc.stdout or proc.stderr)
        try:
            data = json.loads(proc.stdout)
            found = data.get('subject', {}).get('digest', {}).get('sha256') == digest
            coverage = data.get('normalized_result', {}).get('coverage', {}).get('status')
        except ValueError:
            found, coverage = False, None
        entries.append({'binary': name, 'sha256': digest, 'operation': command,
                        'output': out.name, 'exit_code': proc.returncode,
                        'digest_matches': found, 'coverage': coverage})
manifest.write_text(json.dumps(entries, indent=2) + '\n')
print(json.dumps(entries, indent=2))
if any(x['exit_code'] != 0 or not x['digest_matches'] for x in entries):
    raise SystemExit(1)
