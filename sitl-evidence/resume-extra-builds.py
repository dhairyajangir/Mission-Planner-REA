"""Resume the interrupted local SITL builds from their surviving temp tree."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import traceback

base = Path(__file__).resolve().parent
prior = json.loads((base / 'archive-linux-extras-retry-build-status.json').read_text())
work = Path(prior['temp_directory'])
source = work / 'source'
status_file = base / 'archive-linux-extras-resumed-status.json'
if status_file.exists():
    raise FileExistsError('refusing to overwrite previous resume status')
if prior['status'] != 'failed' or not source.is_dir() or not (work / 'python').is_dir():
    raise RuntimeError('expected interrupted build tree is unavailable')
result = {'source_temp_directory': str(source), 'commit': prior['commit'], 'status': 'running', 'steps': [],
          'limitations': prior['limitations']}

def record(step, state, **fields):
    result['steps'].append({'step': step, 'status': state, **fields})
    status_file.write_text(json.dumps(result, indent=2) + '\n')
    print(step + ': ' + state, flush=True)

try:
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    if head != prior['commit']:
        raise ValueError('temporary tree Git revision differs from original build')
    record('verify revision metadata', 'complete', head=head)
    env = os.environ.copy()
    env['PYTHONPATH'] = str(work / 'python')
    for name in ('blimp', 'antennatracker'):
        output = base / 'archive-built-variants' / name
        if output.exists():
            raise FileExistsError(f'refusing to overwrite {output}')
        logfile = base / f'archive-linux-{name}-resumed-build.log'
        record('build ' + name, 'running')
        with logfile.open('wb') as log:
            proc = subprocess.run(['python3', 'waf', name, '-j', '1'], cwd=source,
                                  env=env, stdout=log, stderr=subprocess.STDOUT, timeout=7200)
        if proc.returncode:
            raise RuntimeError(f'{name} build failed: {proc.returncode}; see {logfile.name}')
        binary = source / 'build/sitl/bin' / name
        shutil.copy2(binary, output)
        digest = hashlib.sha256(binary.read_bytes()).hexdigest()
        if hashlib.sha256(output.read_bytes()).hexdigest() != digest:
            raise ValueError('copied binary hash mismatch')
        record('publish ' + name, 'complete', sha256=digest, path=str(output), log=logfile.name)
    result['status'] = 'complete'
    record('all builds', 'complete')
except Exception:
    result['status'] = 'failed'
    result['error'] = traceback.format_exc()
    record('workflow', 'failed')
    raise
