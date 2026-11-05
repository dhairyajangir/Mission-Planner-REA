"""Launch the test-only, path-patched Mission Planner copy and retain output."""
from pathlib import Path
import subprocess

run = Path(__file__).resolve().parent
app = run.parent.parent / 'mission-planner-isolated'
with (run / 'attached-startup.log').open('wb') as log:
    process = subprocess.Popen([str(app / 'MissionPlanner.exe')], cwd=app,
                               stdout=log, stderr=subprocess.STDOUT)
    (run / 'attached-pid.txt').write_text(str(process.pid))
    print(f'launched PID {process.pid}', flush=True)
    code = process.wait()
    (run / 'attached-exit.txt').write_text(str(code))
    print(f'exit {code}', flush=True)
