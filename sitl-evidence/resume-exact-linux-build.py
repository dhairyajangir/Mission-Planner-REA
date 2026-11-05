"""Resume the exact-source /tmp build after adding verified littlefs."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import traceback

evidence = Path(__file__).resolve().parent
project = evidence.parent
previous = json.loads((evidence / 'archive-linux-build-status.json').read_text())
work = Path(previous['temp_directory']).resolve()
if not work.is_relative_to(Path('/tmp')) or not work.name.startswith('ardupilot-sitl-72b23820-'):
    raise ValueError('unexpected temporary build directory')
source = work / 'source'
if not (source / '.git/HEAD').is_file():
    raise FileNotFoundError('temporary source or Git metadata is missing; recreate the build workspace')
tree = json.loads((project / 'research-tools/submodule-archives/littlefs-tree.json').read_text())
provenance = json.loads((project / 'ardupilot-source/archive-provenance.json').read_text())
expected = next(x['sha'] for x in provenance['submodule_gitlinks'] if x['path'] == 'modules/littlefs')
if tree['sha'] != expected or tree['truncated']:
    raise ValueError('littlefs tree mismatch')
blobs = {x['path']: x['sha'] for x in tree['tree'] if x['type'] == 'blob'}
verified = project / 'ardupilot-source/ardupilot-master/modules/littlefs'
found = {}
for p in verified.rglob('*'):
    if p.is_file():
        data = p.read_bytes()
        found[p.relative_to(verified).as_posix()] = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
if found != blobs:
    raise ValueError('workspace littlefs files differ from pinned tree')
target = source / 'modules/littlefs'
shutil.copytree(verified, target, dirs_exist_ok=True)
if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip() != previous['commit']:
    raise ValueError('temporary source revision changed')
status = {'source_dir': str(source), 'commit': previous['commit'], 'littlefs_commit': expected,
          'littlefs_verified_files': len(found), 'status': 'running', 'previous_attempt': 'archive-linux-build-status.json'}
status_file = evidence / 'archive-linux-build-resume-status.json'
status_file.write_text(json.dumps(status, indent=2) + '\n')
env = os.environ.copy()
env['PYTHONPATH'] = str(work / 'python')
logpath = evidence / 'archive-linux-copter-build-2.log'
try:
    with logpath.open('wb') as log:
        p = subprocess.run(['python3', 'waf', 'copter', '-j', '2'], cwd=source, env=env,
                           stdout=log, stderr=subprocess.STDOUT, timeout=2400)
    status['build_exit'] = p.returncode
    if p.returncode:
        raise RuntimeError('build failed; inspect ' + str(logpath))
    binary = source / 'build/sitl/bin/arducopter'
    out = evidence / 'archive-built'
    out.mkdir(exist_ok=True)
    dest = out / 'arducopter'
    if dest.exists():
        raise FileExistsError(dest)
    shutil.copy2(binary, dest)
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    if digest != hashlib.sha256(dest.read_bytes()).hexdigest():
        raise ValueError('binary copy mismatch')
    status.update(status='complete', binary=str(dest), sha256=digest)
except Exception:
    status.update(status='failed', error=traceback.format_exc())
    raise
finally:
    status_file.write_text(json.dumps(status, indent=2) + '\n')
    print(json.dumps(status, indent=2), flush=True)
