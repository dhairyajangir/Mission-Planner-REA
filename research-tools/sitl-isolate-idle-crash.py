"""Does ArduPlane/QuadPlane panic in the simulator on its own, with no MAVLink commands sent at all? Tests whether the crash seen in sitl-mavlink-command-sweep.py (panic in
Location::get_alt_cm, "Location cannot be (0, 0, 0)") is time-triggered rather than caused by any particular command: boots one fresh simulator, connects, and only waits, checking
every 10 s whether the process is still alive, for up to `seconds` (default 180). Simulator only (WSL, pymavlink).

    python3 sitl-isolate-idle-crash.py <ardupilot tree> <out dir> [seconds]
"""
import json
import os
import subprocess
import sys
import time

TREE, OUT = sys.argv[1], sys.argv[2]
SECONDS = float(sys.argv[3]) if len(sys.argv) > 3 else 180.0
sys.path.insert(0, os.path.expanduser('~/custom-gcs'))
from customgcs import link  # noqa: E402

HOME = '-35.363261,149.165230,584,0'
WORK = os.path.expanduser('~/cg-idle')
BIN = os.path.join(TREE, 'build/sitl/bin/arduplane')
DEFAULTS = os.path.join(TREE, 'Tools/autotest/models/plane.parm')


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arduplane'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    proc = subprocess.Popen([BIN, '-w', '--model', 'plane', '-I', '0', '-s', '1', '--home', HOME, '--defaults', DEFAULTS], cwd=WORK,
                            stdout=open(os.path.join(WORK, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    checks = []
    try:
        conn, _ = link.connect(5760, timeout=60.0)
        connected_at = time.time()
        begin = time.time()
        while time.time() - begin < SECONDS:
            time.sleep(10)
            alive = proc.poll() is None
            checks.append({'uptime_s': round(time.time() - connected_at, 1), 'alive': alive})
            print('[idle] uptime %.0f s, alive=%s' % (checks[-1]['uptime_s'], alive), flush=True)
            if not alive:
                break
    except Exception as e:
        checks.append({'exception': repr(e)})
    finally:
        subprocess.call(['pkill', '-x', 'arduplane'])
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
    log_tail = open(os.path.join(WORK, 'sitl.log'), errors='replace').read().splitlines()[-6:]
    json.dump({'checks': checks, 'log_tail': log_tail}, open(os.path.join(OUT, 'idle-crash-result.json'), 'w'), indent=1)
    print('log tail:', log_tail)
    return 0


if __name__ == '__main__':
    sys.exit(main())
