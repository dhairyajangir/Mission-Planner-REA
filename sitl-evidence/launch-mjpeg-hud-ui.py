"""Launch a modified application copy for a local synthetic MJPEG HUD test."""
import os
from pathlib import Path
import subprocess

base = Path(__file__).resolve().parent
project = base.parent
run_name = os.environ.get('MJPEG_HUD_RUN', 'mjpeg-hud-ui')
if Path(run_name).name != run_name:
    raise ValueError('invalid run name')
run = base / run_name
run.mkdir(exist_ok=True)
if (run / 'pid.txt').exists():
    raise FileExistsError('refusing to overwrite prior evidence')
app = project / 'mission-planner-isolated'
runtime = project / 'mission-planner-runtime'
env = os.environ.copy()
env.update({'MP_MJPEG_HUD_RESULT': str(run / 'application-result.txt'),
            'MP_MJPEG_HUD_STOP': str(run / 'stop.txt'), 'USERPROFILE': str(runtime),
            'APPDATA': str(runtime / 'AppData/Roaming'), 'LOCALAPPDATA': str(runtime / 'AppData/Local'),
            'PROGRAMDATA': str(runtime / 'ProgramData')})
with (run / 'application-stdout.log').open('wb') as output:
    process = subprocess.Popen([str(app / 'MissionPlanner.exe'), '-script', str(base / 'mjpeg-hud-script.py')],
                               cwd=app, env=env, stdout=output, stderr=subprocess.STDOUT)
    (run / 'pid.txt').write_text(str(process.pid))
    print('test application PID', process.pid, flush=True)
    code = process.wait()
    (run / 'exit.txt').write_text(str(code))
    print('test application exit', code, flush=True)
