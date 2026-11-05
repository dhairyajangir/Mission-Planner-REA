"""Make an isolated REA copy with a larger managed representation budget."""
import hashlib
import json
import shutil
from pathlib import Path

root = Path(__file__).resolve().parent.parent
source = root / 'research-tools/node_modules/rea-agents'
target = source.with_name('rea-agents-raised-budget')
if target.exists(): raise FileExistsError(target)
if shutil.disk_usage(root).free < 4 * 1024**3: raise RuntimeError('less than 4 GiB free')
shutil.copytree(source, target)
relative = Path('dist/cli-runtime/ManagedSnapshot-C5h4avgc.js')
original = (source / relative).read_bytes()
old = b'MAX_METADATA_REPRESENTATION_BYTES = 64 * 1024 * 1024;'
new = b'MAX_METADATA_REPRESENTATION_BYTES = 256 * 1024 * 1024;'
if original.count(old) != 1: raise ValueError('unexpected REA distribution; refusing modification')
modified = original.replace(old, new, 1)
(target / relative).write_bytes(modified)
record = {'scope': 'isolated REA 6.8.0 CLI copy; raised managed representation budget only',
          'source_file': str(relative), 'old_limit_bytes': 64 * 1024**2,
          'new_limit_bytes': 256 * 1024**2,
          'original_sha256': hashlib.sha256(original).hexdigest(),
          'modified_sha256': hashlib.sha256(modified).hexdigest()}
record_path = root / 'mission-planner-binary-evidence/rea-raised-budget-modification.json'
record_path.write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
