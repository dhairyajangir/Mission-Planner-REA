"""Hold one disposable local SITL process for the separate Windows library probe."""
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import time

base = Path(__file__).resolve().parent
binary = base / 'archive-built/arducopter'
run = base / 'missionplanner-nonfinite-probe'
run.mkdir(exist_ok=True)
if any((run / name).exists() for name in ('ready.json', 'done.txt', 'host-result.json')):
    raise FileExistsError('refusing to reuse prior run')
port = 6900
result = {'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'port': port,
          'scope': 'Disposable Copter SITL, local Windows library harness; no physical aircraft', 'errors': []}
process = None
with (run / 'sitl.log').open('wb') as log:
    try:
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))
        process = subprocess.Popen([str(binary), '-I', '114', '--model', 'quad',
                                    '--home', '-35.363261,149.165230,584,0'], cwd=run,
                                   stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('simulator exited before readiness')
            with socket.socket() as probe:
                if probe.connect_ex(('127.0.0.1', port)) == 0:
                    break
            time.sleep(.5)
        else:
            raise TimeoutError('simulator did not open localhost port')
        (run / 'ready.json').write_text(json.dumps(result, indent=2) + '\n')
        print('READY port=' + str(port), flush=True)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline and not (run / 'done.txt').exists():
            if process.poll() is not None:
                raise RuntimeError('simulator exited during probe')
            time.sleep(1)
        result['done_marker_seen'] = (run / 'done.txt').exists()
    except Exception as exc:
        result['errors'].append(repr(exc))
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        result['simulator_exit_code'] = process.returncode if process else None
        (run / 'host-result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2), flush=True)
if result['errors'] or not result.get('done_marker_seen'):
    raise SystemExit(1)
