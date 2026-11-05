"""Run REA's verifier against saved OGR managed and two native export captures."""
import gzip
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent.parent
base = root / 'mission-planner-binary-evidence'
managed_dir, native_dir = base / 'managed-native-all', base / 'native-exports'
managed_manifest = json.loads((managed_dir / 'manifest.json').read_text())
native_manifest = json.loads((native_dir / 'manifest.json').read_text())
managed_row = next(x for x in managed_manifest['results'] if x['path'] == 'ogr_csharp.dll')
native_rows = [x for x in native_manifest['results'] if x['path'].lower() in
               ('gdal/x86/ogr_wrap.dll', 'gdal/x64/ogr_wrap.dll')]
assert len(native_rows) == 2
with gzip.open(managed_dir / managed_row['evidence'], 'rt', encoding='utf-8') as f: managed = json.load(f)
native = [json.loads((native_dir / x['evidence']).read_text()) for x in native_rows]
payload = {'managed_boundaries': managed, 'native_observations': native}
out = base / 'managed-native-all'
input_path = out / 'ogr-rea-verification-input.json'
output_path = out / 'ogr-rea-verification-output.json'
if input_path.exists() or output_path.exists(): raise FileExistsError(input_path)
input_path.write_text(json.dumps(payload), encoding='utf-8')
node = r'C:\Users\think\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
cli = root / 'research-tools/node_modules/rea-agents/scripts/rea.mjs'
result = subprocess.run([node, str(cli), 'verify-managed-native-boundaries', str(input_path), '--json'],
                        capture_output=True, timeout=180)
output_path.write_bytes(result.stdout or result.stderr)
print('exit', result.returncode)
data = json.loads(result.stdout)
print(json.dumps(data.get('normalized_result', {}), indent=2)[:2500])
if result.returncode: raise SystemExit(result.returncode)
