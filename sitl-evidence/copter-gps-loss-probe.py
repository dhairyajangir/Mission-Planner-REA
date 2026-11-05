"""Observe one GPS outage and recovery in a disposable local Copter SITL."""
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
run = base / 'archive-copter-gps-loss'
run.mkdir(exist_ok=True)
output = run / 'results.json'
if output.exists():
    raise FileExistsError('refusing to overwrite prior results')
port = 6800
result = {'scope': 'Disposable source-built Copter SITL; standalone MAVLink client; no physical aircraft',
          'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
          'checks': {}, 'status_messages': [], 'events': [], 'errors': []}
process = link = log = None
next_heartbeat = 0
started = time.monotonic()

def receive(timeout=1):
    global next_heartbeat
    if time.monotonic() >= next_heartbeat:
        link.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID,
                                0, 0, mavutil.mavlink.MAV_STATE_ACTIVE)
        next_heartbeat = time.monotonic() + 1
    msg = link.recv_match(type=['HEARTBEAT', 'STATUSTEXT', 'PARAM_VALUE', 'GLOBAL_POSITION_INT', 'GPS_RAW_INT', 'EKF_STATUS_REPORT'],
                          blocking=True, timeout=timeout)
    if msg and msg.get_type() == 'STATUSTEXT':
        result['status_messages'].append(str(msg.text))
        result['events'].append({'seconds': round(time.monotonic() - started, 3), 'type': 'STATUSTEXT', 'text': str(msg.text)})
    elif msg and msg.get_type() == 'HEARTBEAT':
        result['events'].append({'seconds': round(time.monotonic() - started, 3), 'type': 'HEARTBEAT',
                                 'mode': msg.custom_mode, 'armed': bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)})
    elif msg and msg.get_type() == 'GPS_RAW_INT':
        result['events'].append({'seconds': round(time.monotonic() - started, 3), 'type': 'GPS_RAW_INT',
                                 'fix_type': msg.fix_type, 'satellites_visible': msg.satellites_visible})
    elif msg and msg.get_type() == 'EKF_STATUS_REPORT':
        result['events'].append({'seconds': round(time.monotonic() - started, 3), 'type': 'EKF_STATUS_REPORT', 'flags': msg.flags})
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
        probe.bind(('127.0.0.1', port))
    log = (run / 'sitl.log').open('wb')
    process = subprocess.Popen([str(binary), '-I', '104', '--model', 'quad',
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
    gps_enabled = set_param('SIM_GPS1_ENABLE', 1)
    result['checks']['gps_initially_enabled'] = {'passed': gps_enabled == 1, 'value': gps_enabled}
    if gps_enabled != 1:
        raise RuntimeError('simulated GPS enable was not confirmed')
    modes = link.mode_mapping()
    guided, land = modes['GUIDED'], modes['LAND']
    link.set_mode(guided)
    if not wait_mode(guided, 20):
        raise RuntimeError('GUIDED not observed')
    deadline, next_arm, armed = time.monotonic() + 70, 0, False
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
    peak, initial_fix = 0.0, None
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        msg = receive()
        if msg and msg.get_type() == 'GLOBAL_POSITION_INT':
            peak = max(peak, msg.relative_alt / 1000.0)
        if msg and msg.get_type() == 'GPS_RAW_INT' and msg.fix_type >= 3:
            initial_fix = msg.fix_type
        if peak >= 3 and initial_fix is not None:
            break
    result['checks']['takeoff_and_initial_fix'] = {'passed': peak >= 3 and initial_fix is not None,
                                                   'peak_relative_alt_m': peak, 'fix_type': initial_fix}
    if not result['checks']['takeoff_and_initial_fix']['passed']:
        raise RuntimeError('takeoff altitude or initial GPS fix not observed')
    disabled = set_param('SIM_GPS1_ENABLE', 0)
    result['events'].append({'seconds': round(time.monotonic() - started, 3), 'type': 'gps_disable_confirmed'})
    result['checks']['gps_disabled'] = {'passed': disabled == 0, 'value': disabled}
    if disabled != 0:
        raise RuntimeError('simulated GPS disable not confirmed')
    # Observe before restoring GPS; record actual behavior without assuming an EKF mode transition.
    deadline, loss_seen, lowest_fix = time.monotonic() + 25, False, 255
    while time.monotonic() < deadline:
        msg = receive()
        if msg and msg.get_type() == 'GPS_RAW_INT':
            lowest_fix = min(lowest_fix, msg.fix_type)
            loss_seen |= msg.fix_type < 3
    result['checks']['gps_fix_lost'] = {'passed': loss_seen, 'lowest_fix_type': lowest_fix if lowest_fix != 255 else None}
    restored = set_param('SIM_GPS1_ENABLE', 1)
    result['events'].append({'seconds': round(time.monotonic() - started, 3), 'type': 'gps_restore_confirmed'})
    result['checks']['gps_reenabled'] = {'passed': restored == 1, 'value': restored}
    deadline, recovered_fix = time.monotonic() + 60, None
    while time.monotonic() < deadline:
        msg = receive()
        if msg and msg.get_type() == 'GPS_RAW_INT' and msg.fix_type >= 3:
            recovered_fix = msg.fix_type
            break
    result['checks']['gps_fix_recovered'] = {'passed': recovered_fix is not None, 'fix_type': recovered_fix}
    link.set_mode(land)
    land_seen = wait_mode(land, 25)
    result['checks']['land_requested'] = {'passed': land_seen, 'mode': land}
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
    result['passed'] = not result['errors'] and len(result['checks']) == 9 and all(v['passed'] for v in result['checks'].values())
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
if not result['passed']:
    raise SystemExit(1)
