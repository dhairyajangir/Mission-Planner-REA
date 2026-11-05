"""Launch the existing patched application with a bounded local test script."""
import os
from pathlib import Path
import subprocess
base = Path(__file__).resolve().parent
project = base.parent
run = base / 'ui-calibration-armed'
run.mkdir(exist_ok=True)
if (run / 'pid.txt').exists(): raise FileExistsError('run already exists')
app = project / 'mission-planner-isolated'
runtime = project / 'mission-planner-runtime'
env = os.environ.copy()
env.update({'MP_INTEGRATED_RESULT': str(run / 'application-result.txt'),
            'MP_SPOOL_DIR': str(run / 'spool'), 'MP_STOP_PATH': str(run / 'ui-stop.txt'),
            'USERPROFILE': str(runtime), 'APPDATA': str(runtime / 'AppData/Roaming'),
            'LOCALAPPDATA': str(runtime / 'AppData/Local'), 'PROGRAMDATA': str(runtime / 'ProgramData')})
with (run / 'application-stdout.log').open('wb') as output:
    process = subprocess.Popen([str(app / 'MissionPlanner.exe'), '-script', str(base / 'ui-calibration-armed-script.py')],
                               cwd=app, env=env, stdout=output, stderr=subprocess.STDOUT)
    (run / 'pid.txt').write_text(str(process.pid))
    print('test application PID', process.pid, flush=True)
    code = process.wait()
    (run / 'exit.txt').write_text(str(code))
    print('test application exit', code, flush=True)
