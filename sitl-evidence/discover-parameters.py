"""Read selected candidate parameters from one isolated SITL instance."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import traceback

base = Path(__file__).resolve().parent
sys.path.insert(0, str(base / 'python'))
from pymavlink import mavutil

run = base / 'parameter-discovery'
run.mkdir(exist_ok=True)
result = {'scope': 'read-only ArduCopter 4.7.2 SITL discovery', 'parameters': {}, 'errors': []}
proc = link = log = None
try:
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 6180))
    log = (run / 'sitl.log').open('wb')
    proc = subprocess.Popen([str(base / 'arducopter'), '-I', '42', '--model', 'quad',
                             '--home=-35.363261,149.165230,584,0'], cwd=run,
                            stdout=log, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f'SITL exited: {proc.returncode}')
        try:
            link = mavutil.mavlink_connection('tcp:127.0.0.1:6180', source_system=255)
            break
        except OSError:
            time.sleep(.5)
    if link is None or link.wait_heartbeat(timeout=30) is None:
        raise TimeoutError('No heartbeat')
    link.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,
                            mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0,
                            mavutil.mavlink.MAV_STATE_ACTIVE)
    time.sleep(15)
    for name in ('WPNAV_SPEED', 'LOG_DISARMED', 'FRAME_CLASS', 'SIM_SPEEDUP', 'RTL_ALT_M'):
        link.mav.param_request_read_send(link.target_system, 1, name.encode(), -1)
        deadline = time.monotonic() + 5
        value = None
        while time.monotonic() < deadline:
            msg = link.recv_match(type='PARAM_VALUE', blocking=True, timeout=1)
            if msg and str(msg.param_id).rstrip('\x00') == name:
                value = {'value': msg.param_value, 'type': msg.param_type, 'count': msg.param_count}
                break
        result['parameters'][name] = value
except Exception:
    result['errors'].append(traceback.format_exc())
finally:
    if link:
        link.close()
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
    if log:
        log.close()
    (run / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
sys.exit(1 if result['errors'] else 0)
