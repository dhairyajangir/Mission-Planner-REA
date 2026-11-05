"""Start the disposable quad simulator for the armed calibration UI test."""
from pathlib import Path
import subprocess
import time
base = Path(__file__).resolve().parent
run = base / 'ui-calibration-armed'
run.mkdir(exist_ok=True)
binary = base / 'archive-built/arducopter'
with (run / 'sitl.log').open('wb') as output:
    process = subprocess.Popen([str(binary), '-I', '153', '--model', 'quad',
                                '--home=-35.363261,149.165230,584,0'], cwd=run,
                               stdout=output, stderr=subprocess.STDOUT)
    (run / 'sitl-pid.txt').write_text(str(process.pid))
    try:
        end = time.monotonic() + 600
        while time.monotonic() < end and not (run / 'stop.txt').exists() and process.poll() is None:
            time.sleep(0.2)
    finally:
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        (run / 'sitl-exit.txt').write_text(str(process.returncode))
print('simulator stopped')
