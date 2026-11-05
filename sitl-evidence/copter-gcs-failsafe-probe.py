"""Test a GCS heartbeat timeout only in a disposable local Copter simulator."""
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
run = base / 'archive-copter-gcs-failsafe'
run.mkdir(exist_ok=True)
output = run / 'results.json'
if output.exists():
    raise FileExistsError('refusing to overwrite prior results')
port = 6430
result = {'scope': 'Disposable source-built Copter SITL; standalone MAVLink client, no physical aircraft',
          'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'checks': {},
          'status_messages': [], 'errors': []}
process = link = log = None
next_heartbeat = 0

def receive(timeout=1, send_heartbeat=True):
    global next_heartbeat
    if send_heartbeat and time.monotonic() >= next_heartbeat:
        link.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID,
                                0, 0, mavutil.mavlink.MAV_STATE_ACTIVE)
        next_heartbeat = time.monotonic() + 1
    msg = link.recv_match(type=['HEARTBEAT', 'STATUSTEXT', 'PARAM_VALUE', 'GLOBAL_POSITION_INT', 'COMMAND_ACK'],
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
            return abs(msg.param_value - value) < 0.01
    return False

def wait_mode(mode, timeout, send_heartbeat=True):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        msg = receive(send_heartbeat=send_heartbeat)
        if msg and msg.get_type() == 'HEARTBEAT' and msg.custom_mode == mode:
            return True
    return False

try:
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', port))
    log = (run / 'sitl.log').open('wb')
    process = subprocess.Popen([str(binary), '-I', '67', '--model', 'quad',
                                '--home', '-35.363261,149.165230,584,0'], cwd=run,
                               stdout=log, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('simulator exited before connection')
        try:
            link = mavutil.mavlink_connection(f'tcp:127.0.0.1:{port}', source_system=255)
            break
        except OSError:
            time.sleep(.5)
    if link is None or not link.wait_heartbeat(timeout=30):
        raise TimeoutError('no simulator heartbeat')
    link.mav.request_data_stream_send(link.target_system, link.target_component,
                                      mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1)
    # Fresh disposable simulator only. Keep sending GCS heartbeats until the failure phase.
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        receive()
    timeout_set = set_param('FS_GCS_TIMEOUT', 5)
    action_set = set_param('FS_GCS_ENABLE', 1)
    result['checks']['configure_failsafe'] = {'passed': timeout_set and action_set,
                                               'timeout_seconds': 5, 'action': 'RTL'}
    if not timeout_set or not action_set:
        raise RuntimeError('simulator did not confirm failsafe parameters')
    modes = link.mode_mapping()
    guided, rtl, land = modes['GUIDED'], modes['RTL'], modes['LAND']
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
                               mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, 5)
    peak = 0.0
    deadline = time.monotonic() + 70
    while time.monotonic() < deadline:
        msg = receive()
        if msg and msg.get_type() == 'GLOBAL_POSITION_INT':
            peak = max(peak, msg.relative_alt / 1000.0)
            if peak >= 3:
                break
    result['checks']['takeoff'] = {'passed': peak >= 3, 'peak_relative_alt_m': peak}
    if peak < 3:
        raise RuntimeError('takeoff altitude not reached')
    # Keep the socket open but deliberately stop transmitting GCS heartbeats.
    switched = wait_mode(rtl, 35, send_heartbeat=False)
    result['checks']['gcs_timeout_rtl'] = {'passed': switched, 'rtl_mode': rtl}
    if not switched:
        raise RuntimeError('RTL was not observed after heartbeat loss')
    # End the simulated run in LAND while transmitting heartbeats again.
    link.set_mode(land)
    result['checks']['land_mode'] = {'passed': wait_mode(land, 20)}
    disarmed = False
    deadline = time.monotonic() + 90
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
