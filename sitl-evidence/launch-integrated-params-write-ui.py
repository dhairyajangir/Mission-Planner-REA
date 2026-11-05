"""Launch an isolated app copy for a bounded local parameter-write UI test."""
import os
from pathlib import Path
import subprocess

base = Path(__file__).resolve().parent
project = base.parent
run = base / 'integrated-ui-params-write'
run.mkdir(exist_ok=True)
if (run / 'pid.txt').exists():
    raise FileExistsError('refusing to overwrite prior application evidence')
app = project / 'mission-planner-isolated'
runtime = project / 'mission-planner-runtime'
env = os.environ.copy()
env.update({'MP_INTEGRATED_RESULT': str(run / 'application-result.txt'),
            'MP_SPOOL_DIR': str(run / 'spool'), 'MP_READBACK_MARKER': str(run / 'readback-requested.txt'),
            'USERPROFILE': str(runtime), 'APPDATA': str(runtime / 'AppData/Roaming'),
            'LOCALAPPDATA': str(runtime / 'AppData/Local'), 'PROGRAMDATA': str(runtime / 'ProgramData')})
with (run / 'application-stdout.log').open('wb') as output:
    process = subprocess.Popen([str(app / 'MissionPlanner.exe'), '-script', str(base / 'integrated-ui-params-write-probe.py')],
                               cwd=app, env=env, stdout=output, stderr=subprocess.STDOUT)
    (run / 'pid.txt').write_text(str(process.pid))
    print('test application PID', process.pid, flush=True)
    code = process.wait()
    (run / 'exit.txt').write_text(str(code))
    print('test application exit', code, flush=True)
