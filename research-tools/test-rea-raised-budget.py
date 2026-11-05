"""Capture a single bounded REA selection using the separately modified copy."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
assembly, selection = sys.argv[1:3]
if Path(assembly).name != assembly or not all(part.isidentifier() for part in selection.split('.')):
    raise ValueError('invalid input')
out = root / 'mission-planner-binary-evidence/rea-raised-budget'
out.mkdir(exist_ok=True)
stem = Path(assembly).stem.lower().replace('.', '-') + '-' + selection.lower().replace('.', '-')
temporary, result = out / (stem + '.tmp.json'), out / (stem + '.json.gz')
if temporary.exists() or result.exists(): raise FileExistsError(stem)
if shutil.disk_usage(root).free < 4 * 1024**3: raise RuntimeError('less than 4 GiB free')
node = r'C:\Users\think\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
cli = root / 'research-tools/node_modules/rea-agents-raised-budget/scripts/rea.mjs'
binary = root / 'mission-planner-portable' / assembly
with temporary.open('wb') as stream:
    proc = subprocess.run([node, '--max-old-space-size=2048', str(cli), 'inspect-managed-members',
                           str(binary), '--type', selection, '--json'], stdout=stream,
                          stderr=subprocess.PIPE, timeout=300)
try:
    data = json.loads(temporary.read_text(encoding='utf-8'))
    normalized = data['normalized_result']
    coverage = normalized['coverage']
    assert data['subject']['digest']['sha256'] == hashlib.sha256(binary.read_bytes()).hexdigest()
    with temporary.open('rb') as src, gzip.open(result, 'wb', compresslevel=6) as dst:
        shutil.copyfileobj(src, dst)
    report = {'assembly': assembly, 'selection': selection, 'process_exit': proc.returncode,
              'coverage': coverage, 'types': len(normalized.get('types', [])),
              'methods': len(normalized.get('methods', [])), 'capture_sha256': hashlib.sha256(result.read_bytes()).hexdigest(),
              'tool_modification': '../rea-raised-budget-modification.json'}
    (out / (stem + '-summary.json')).write_text(json.dumps(report, indent=2) + '\n')
    temporary.unlink()
    print(json.dumps(report, indent=2))
except Exception:
    (out / (stem + '-stderr.txt')).write_bytes(proc.stderr)
    raise
