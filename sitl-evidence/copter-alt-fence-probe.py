"""Trigger a maximum-altitude fence only in a disposable local Copter SITL."""
import hashlib
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

binary = base / 'archive-built/arducopter'
run = base / 'archive-copter-alt-fence'
run.mkdir(exist_ok=True)
output = run / 'results.json'
if output.exists():
    raise FileExistsError('refusing to overwrite prior results')
result = {'scope': 'Disposable source-built Copter SITL; standalone MAVLink client; no physical aircraft',
          'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
          'checks': {}, 'status_messages': [], 'errors': []}
process = link = log = None
next_heartbeat = 0


def receive(timeout=1):
    global next_heartbeat
    if time.monotonic() >= next_heartbeat:
        link.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID,
                                0, 0, mavutil.mavlink.MAV_STATE_ACTIVE)
        next_heartbeat = time.monotonic() + 1
    msg = link.recv_match(type=['HEARTBEAT', 'STATUSTEXT', 'PARAM_VALUE', 'GLOBAL_POSITION_INT', 'FENCE_STATUS'],
                          blocking=True, timeout=timeout)
    if msg and msg.get_type() == 'STATUSTEXT':
        result['status_messages'].append(str(msg.text))
    return msg


def set_param(name, value):
    link.mav.param_set_send(link.target_system, link.target_component, name.encode('ascii'), value,
                            mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        msg = receive()
        if msg and msg.get_type() == 'PARAM_VALUE' and str(msg.param_id).rstrip('\x00') == name:
            return msg.param_value
    raise TimeoutError('parameter response missing: ' + name)


def wait_mode(mode, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        msg = receive()
        if msg and msg.get_type() == 'HEARTBEAT' and msg.custom_mode == mode:
            return True
    return False


try:
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 6680))
    log = (run / 'sitl.log').open('wb')
    process = subprocess.Popen([str(binary), '-I', '92', '--model', 'quad',
                                '--home', '-35.363261,149.165230,584,0'], cwd=run,
                               stdout=log, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('simulator exited before connection')
        try:
            link = mavutil.mavlink_connection('tcp:127.0.0.1:6680', source_system=255)
            break
        except OSError:
            time.sleep(.5)
    if link is None or not link.wait_heartbeat(timeout=30):
        raise TimeoutError('no simulator heartbeat')
    link.mav.request_data_stream_send(link.target_system, link.target_component,
                                      mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1)
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        receive()
    settings = {}
    for name, value in (('FENCE_ENABLE', 0), ('FENCE_TYPE', 1), ('FENCE_ALT_MAX', 10), ('FENCE_ACTION', 2)):
        settings[name] = set_param(name, value)
    result['checks']['configuration'] = {'passed': settings == {'FENCE_ENABLE': 0, 'FENCE_TYPE': 1,
                                                                 'FENCE_ALT_MAX': 10, 'FENCE_ACTION': 2},
                                         'values': settings}
    if not result['checks']['configuration']['passed']:
        raise RuntimeError('fence settings not confirmed')
    modes = link.mode_mapping()
    guided, land = modes['GUIDED'], modes['LAND']
    link.set_mode(guided)
    if not wait_mode(guided, 20):
        raise RuntimeError('GUIDED not observed')
    deadline, next_arm = time.monotonic() + 70, 0
    armed = False
    while time.monotonic() < deadline:
        if time.monotonic() >= next_arm:
            link.arducopter_arm()
            next_arm = time.monotonic() + 8
        msg = receive()
        if msg and msg.get_type() == 'HEARTBEAT' and msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
            armed = True
            break
    result['checks']['armed'] = {'passed': armed}
    if not armed:
        raise RuntimeError('normal arming checks did not pass')
    link.mav.command_long_send(link.target_system, link.target_component,
                               mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, 15)
    peak = 0.0
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        msg = receive()
        if msg and msg.get_type() == 'GLOBAL_POSITION_INT':
            peak = max(peak, msg.relative_alt / 1000.0)
            if peak >= 11.5:
                break
    result['checks']['above_limit_before_enable'] = {'passed': peak >= 11.5, 'relative_alt_m': peak}
    if peak < 11.5:
        raise RuntimeError('target altitude not reached')
    enabled = set_param('FENCE_ENABLE', 1)
    result['checks']['fence_enabled'] = {'passed': enabled == 1, 'value': enabled}
    landed_mode = wait_mode(land, 35)
    result['checks']['fence_land_mode'] = {'passed': landed_mode, 'mode': land}
    if not landed_mode:
        raise RuntimeError('LAND mode not observed after enabling breached fence')
    disarmed = False
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        msg = receive()
        if msg and msg.get_type() == 'HEARTBEAT' and not (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED):
            disarmed = True
            break
    result['checks']['disarmed'] = {'passed': disarmed}
except Exception:
    result['errors'].append(traceback.format_exc())
finally:
    if link:
        link.close()
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    if log:
        log.close()
    result['passed'] = not result['errors'] and len(result['checks']) == 6 and all(v['passed'] for v in result['checks'].values())
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
if not result['passed']:
    raise SystemExit(1)
