"""Open the captured simulator log in the isolated Mission Planner test copy."""
import os
from pathlib import Path
import subprocess

base = Path(__file__).resolve().parent
project = base.parent
run = base / 'isolated-log-browser'
run.mkdir(exist_ok=True)
app = project / 'mission-planner-isolated'
runtime = project / 'mission-planner-runtime'
source_log = base / 'nonempty-log-probe/downloaded.bin'
env = os.environ.copy()
env.update({'USERPROFILE': str(runtime), 'APPDATA': str(runtime / 'AppData/Roaming'),
            'LOCALAPPDATA': str(runtime / 'AppData/Local'), 'PROGRAMDATA': str(runtime / 'ProgramData')})
with (run / 'application-stdout.log').open('wb') as output:
    process = subprocess.Popen([str(app / 'MissionPlanner.exe'), str(source_log)], cwd=app,
                               env=env, stdout=output, stderr=subprocess.STDOUT)
    (run / 'pid.txt').write_text(str(process.pid))
    print('test application PID', process.pid, flush=True)
    exit_code = process.wait()
    (run / 'exit.txt').write_text(str(exit_code))
    print('test application exit', exit_code, flush=True)
