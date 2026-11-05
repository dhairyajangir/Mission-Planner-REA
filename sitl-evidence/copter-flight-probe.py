"""Exercise guided takeoff and landing on the locally built SITL only."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import traceback

base = Path(__file__).resolve().parent
sys.path.insert(0, str(base / 'python'))
from pymavlink import mavutil

binary = base / 'archive-built/arducopter'
run_name = os.environ.get('SITL_FLIGHT_RUN', 'archive-copter-flight')
if Path(run_name).name != run_name:
    raise ValueError('SITL_FLIGHT_RUN must be a directory name')
run = base / run_name
run.mkdir(exist_ok=True)
output = run / 'results.json'
if output.exists():
    raise FileExistsError('refusing to overwrite prior results')
instance = 66
port = 5760 + instance * 10
result = {'scope': 'Local source-built ArduCopter SITL only; no Mission Planner or physical aircraft',
          'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'checks': {}, 'errors': [],
          'status_messages': [], 'command_acknowledgements': []}
process = link = log = None

def heartbeat_until(predicate, timeout, retry_arm=False):
    deadline = time.monotonic() + timeout
    next_arm = time.monotonic() + 8
    while time.monotonic() < deadline:
        if retry_arm and time.monotonic() >= next_arm:
            link.arducopter_arm()
            next_arm = time.monotonic() + 8
        message = link.recv_match(type=['HEARTBEAT', 'STATUSTEXT', 'COMMAND_ACK'], blocking=True, timeout=1)
        if not message:
            continue
        if message.get_type() == 'STATUSTEXT':
            result['status_messages'].append(str(message.text))
        elif message.get_type() == 'COMMAND_ACK':
            result['command_acknowledgements'].append({'command': message.command, 'result': message.result})
        elif predicate(message):
            return message
    return None

try:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', port))
    log = (run / 'sitl.log').open('wb')
    process = subprocess.Popen([str(binary), '-I', str(instance), '--model', 'quad',
                                '--home', '-35.363261,149.165230,584,0'], cwd=run,
                               stdout=log, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('simulator exited before connecting')
        try:
            link = mavutil.mavlink_connection(f'tcp:127.0.0.1:{port}', source_system=255)
            break
        except OSError:
            time.sleep(0.5)
    if link is None or not link.wait_heartbeat(timeout=30):
        raise TimeoutError('no simulator heartbeat')
    link.mav.request_data_stream_send(link.target_system, link.target_component,
                                      mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1)
    # Allow simulated GPS and estimator startup; do not bypass arming checks.
    time.sleep(25)
    guided = link.mode_mapping().get('GUIDED')
    land = link.mode_mapping().get('LAND')
    if guided is None or land is None:
        raise RuntimeError('expected Copter modes are unavailable')
    link.set_mode(guided)
    hb = heartbeat_until(lambda msg: msg.custom_mode == guided, 20)
    result['checks']['guided_mode'] = {'passed': hb is not None, 'mode': guided}
    if hb is None:
        raise RuntimeError('GUIDED mode not confirmed')
    link.arducopter_arm()
    hb = heartbeat_until(lambda msg: bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED), 65, retry_arm=True)
    result['checks']['armed'] = {'passed': hb is not None}
    if hb is None:
        raise RuntimeError('simulator did not arm with its normal checks')
    link.mav.command_long_send(link.target_system, link.target_component,
                               mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, 5)
    peak = 0.0
    deadline = time.monotonic() + 70
    while time.monotonic() < deadline:
        position = link.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=1)
        if position:
            peak = max(peak, position.relative_alt / 1000.0)
            if peak >= 3.0:
                break
    result['checks']['takeoff'] = {'passed': peak >= 3.0, 'peak_relative_alt_m': peak}
    link.set_mode(land)
    hb = heartbeat_until(lambda msg: msg.custom_mode == land, 20)
    result['checks']['land_mode'] = {'passed': hb is not None, 'mode': land}
    hb = heartbeat_until(lambda msg: not (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED), 90)
    result['checks']['landed_and_disarmed'] = {'passed': hb is not None}
except Exception:
    result['errors'].append(traceback.format_exc())
finally:
    if link is not None:
        link.close()
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    if log is not None:
        log.close()
    result['passed'] = not result['errors'] and len(result['checks']) == 5 and all(x['passed'] for x in result['checks'].values())
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
if not result['passed']:
    raise SystemExit(1)
