"""Test GCS heartbeat loss on a stationary disposable Rover simulator."""
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

binary = base / 'archive-built-variants/ardurover'
run = base / 'archive-rover-gcs-failsafe-3'
run.mkdir(exist_ok=True)
output = run / 'results.json'
if output.exists():
    raise FileExistsError('refusing to overwrite prior results')
port = 6780
result = {'scope': 'Stationary source-built Rover SITL; standalone MAVLink client; no physical vehicle',
          'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'checks': {},
          'status_messages': [], 'events': [], 'errors': []}
process = link = log = None
next_heartbeat = 0
started = time.monotonic()

def receive(timeout=1, send_heartbeat=True):
    global next_heartbeat
    if send_heartbeat and time.monotonic() >= next_heartbeat:
        link.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID,
                                0, 0, mavutil.mavlink.MAV_STATE_ACTIVE)
        next_heartbeat = time.monotonic() + 1
    msg = link.recv_match(type=['HEARTBEAT', 'STATUSTEXT', 'PARAM_VALUE'], blocking=True, timeout=timeout)
    if msg and msg.get_type() == 'STATUSTEXT':
        result['status_messages'].append(str(msg.text))
        result['events'].append({'seconds': round(time.monotonic() - started, 3), 'kind': 'status', 'text': str(msg.text)})
    elif msg and msg.get_type() == 'HEARTBEAT':
        result['events'].append({'seconds': round(time.monotonic() - started, 3), 'kind': 'heartbeat',
                                 'mode': msg.custom_mode, 'armed': bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED),
                                 'sending_heartbeats': send_heartbeat})
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

def wait_mode(mode, timeout, heartbeats=True):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        msg = receive(send_heartbeat=heartbeats)
        if msg and msg.get_type() == 'HEARTBEAT' and msg.custom_mode == mode:
            return True
    return False

try:
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', port))
    log = (run / 'sitl.log').open('wb')
    process = subprocess.Popen([str(binary), '-I', '102', '--model', 'rover',
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
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        receive()
    expected = {'FS_THR_ENABLE': 0, 'FS_GCS_ENABLE': 1, 'FS_GCS_TIMEOUT': 3, 'FS_TIMEOUT': 1, 'FS_ACTION': 2}
    values = {name: set_param(name, value) for name, value in expected.items()}
    result['checks']['configuration'] = {'passed': values == expected, 'values': values}
    if values != expected:
        raise RuntimeError('failsafe parameters not confirmed')
    modes = link.mode_mapping()
    guided, hold = modes['GUIDED'], modes['HOLD']
    link.set_mode(guided)
    if not wait_mode(guided, 20):
        raise RuntimeError('GUIDED mode not observed')
    deadline, next_arm, armed = time.monotonic() + 70, 0, False
    while time.monotonic() < deadline:
        if time.monotonic() >= next_arm:
            link.arducopter_arm()
            next_arm = time.monotonic() + 8
        msg = receive()
        if msg and msg.get_type() == 'HEARTBEAT' and msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
            armed = True
            break
    result['checks']['armed_guided'] = {'passed': armed, 'guided_mode': guided}
    if not armed:
        raise RuntimeError('normal arming checks did not pass')
    # Keep the vehicle stationary: no velocity, waypoint or steering command is sent.
    hold_seen = False
    loss_started = time.monotonic()
    result['events'].append({'seconds': round(loss_started - started, 3), 'kind': 'stop_gcs_heartbeats'})
    deadline = loss_started + 30
    while time.monotonic() < deadline:
        msg = receive(send_heartbeat=False)
        if msg and msg.get_type() == 'HEARTBEAT' and msg.custom_mode == hold:
            hold_seen = True
        if hold_seen and 'GCS Failsafe' in result['status_messages']:
            break
    result['checks']['gcs_loss_hold'] = {'passed': hold_seen and 'GCS Failsafe' in result['status_messages'],
                                         'hold_mode': hold, 'hold_seen': hold_seen,
                                         'gcs_failsafe_notice': 'GCS Failsafe' in result['status_messages']}
    if not result['checks']['gcs_loss_hold']['passed']:
        raise RuntimeError('HOLD and GCS failsafe notice not both observed')
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and 'GCS Failsafe Cleared' not in result['status_messages']:
        receive()
    cleared = 'GCS Failsafe Cleared' in result['status_messages']
    result['checks']['gcs_recovered'] = {'passed': cleared}
    link.arducopter_disarm()
    deadline, disarmed = time.monotonic() + 20, False
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
    result['passed'] = not result['errors'] and len(result['checks']) == 5 and all(v['passed'] for v in result['checks'].values())
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
if not result['passed']:
    raise SystemExit(1)
