"""Compare original and raised-budget REA outputs for a bounded selection."""
import hashlib
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent.parent
node = r'C:\Users\think\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
binary = root / 'mission-planner-portable/Accord.Math.dll'
out = root / 'mission-planner-binary-evidence/rea-raised-budget'
results = []
for variant in ('rea-agents', 'rea-agents-raised-budget'):
    cli = root / 'research-tools/node_modules' / variant / 'scripts/rea.mjs'
    proc = subprocess.run([node, str(cli), 'inspect-managed-members', str(binary), '--type',
                           'AForge.Math.Gaussian', '--json'], capture_output=True, check=True, timeout=120)
    path = out / (variant + '-gaussian.json')
    if path.exists(): raise FileExistsError(path)
    path.write_bytes(proc.stdout)
    results.append(json.loads(proc.stdout))
assert results[0]['normalized_result'] == results[1]['normalized_result']
report = {'assembly_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
          'selection': 'AForge.Math.Gaussian', 'normalized_results_equal': True,
          'coverage': results[0]['normalized_result']['coverage'],
          'capture_sha256': {v: hashlib.sha256((out / (v + '-gaussian.json')).read_bytes()).hexdigest()
                             for v in ('rea-agents', 'rea-agents-raised-budget')}}
(out / 'variant-comparison.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
