"""Launch the isolated application with the cache-only synthetic map script."""
import os
from pathlib import Path
import subprocess

base = Path(__file__).resolve().parent
project = base.parent
run = base / 'offline-map-ui'
run.mkdir(exist_ok=True)
app = project / 'mission-planner-isolated'
runtime = project / 'mission-planner-runtime'
env = os.environ.copy()
env.update({'MP_OFFLINE_MAP_RESULT': str(run / 'application-result.txt'),
            'USERPROFILE': str(runtime), 'APPDATA': str(runtime / 'AppData/Roaming'),
            'LOCALAPPDATA': str(runtime / 'AppData/Local'), 'PROGRAMDATA': str(runtime / 'ProgramData')})
with (run / 'application-stdout.log').open('wb') as output:
    process = subprocess.Popen([str(app / 'MissionPlanner.exe'), '-script', str(base / 'offline-map-script.py')],
                               cwd=app, env=env, stdout=output, stderr=subprocess.STDOUT)
    (run / 'pid.txt').write_text(str(process.pid))
    print('test application PID', process.pid, flush=True)
    exit_code = process.wait()
    (run / 'exit.txt').write_text(str(exit_code))
    print('test application exit', exit_code, flush=True)
