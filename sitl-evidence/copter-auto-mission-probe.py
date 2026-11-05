"""Upload and execute a short mission on a disposable local Copter simulator."""
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
run = base / 'archive-copter-auto-mission'
run.mkdir(exist_ok=True)
output = run / 'results.json'
if output.exists():
    raise FileExistsError('refusing to overwrite prior results')
port = 6450
result = {'scope': 'Disposable source-built Copter SITL; standalone MAVLink client; no physical aircraft',
          'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
          'checks': {}, 'status_messages': [], 'mission_current': [], 'mission_reached': [], 'errors': []}
process = link = log = None

def wait_heartbeat(predicate, seconds, retry_arm=False):
    deadline, retry = time.monotonic() + seconds, time.monotonic() + 8
    while time.monotonic() < deadline:
        if retry_arm and time.monotonic() >= retry:
            link.arducopter_arm()
            retry = time.monotonic() + 8
        msg = link.recv_match(type=['HEARTBEAT', 'STATUSTEXT'], blocking=True, timeout=1)
        if msg and msg.get_type() == 'STATUSTEXT':
            result['status_messages'].append(str(msg.text))
        elif msg and predicate(msg):
            return msg
    return None

try:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', port))
    log = (run / 'sitl.log').open('wb')
    process = subprocess.Popen([str(binary), '-I', '69', '--model', 'quad',
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
    system, component = link.target_system, link.target_component
    link.mav.request_data_stream_send(system, component, mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1)
    time.sleep(25)
    # Enable the documented simulated Auto takeoff option; do not disable arming checks.
    link.mav.param_set_send(system, component, b'AUTO_OPTIONS', 2, mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
    deadline, configured = time.monotonic() + 15, False
    while time.monotonic() < deadline:
        msg = link.recv_match(type='PARAM_VALUE', blocking=True, timeout=1)
        if msg and str(msg.param_id).rstrip('\x00') == 'AUTO_OPTIONS' and int(msg.param_value) == 2:
            configured = True
            break
    result['checks']['auto_option'] = {'passed': configured, 'value': 2}
    if not configured:
        raise RuntimeError('AUTO_OPTIONS not confirmed')
    # Home, takeoff, nearby waypoint, land. Coordinates are simulation only.
    lat, lon = -353632610, 1491652300
    items = [(mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, lat, lon, 0),
             (mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, lat, lon, 5),
             (mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, lat + 300, lon, 5),
             (mavutil.mavlink.MAV_CMD_NAV_LAND, lat + 300, lon, 0)]
    link.mav.mission_count_send(system, component, len(items))
    sent, ack = set(), None
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        msg = link.recv_match(type=['MISSION_REQUEST_INT', 'MISSION_REQUEST', 'MISSION_ACK'], blocking=True, timeout=1)
        if not msg:
            continue
        if msg.get_type() == 'MISSION_ACK':
            ack = msg.type
            break
        if msg.seq >= len(items):
            raise ValueError(f'unexpected mission index {msg.seq}')
        command, x, y, z = items[msg.seq]
        link.mav.mission_item_int_send(system, component, msg.seq, mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                                       command, 0, 1, 0, 0, 0, 0, x, y, z)
        sent.add(msg.seq)
    result['checks']['upload'] = {'passed': ack == 0 and sent == set(range(len(items))),
                                  'ack': ack, 'sent': sorted(sent)}
    if not result['checks']['upload']['passed']:
        raise RuntimeError('mission upload not accepted')
    modes = link.mode_mapping()
    link.set_mode(modes['GUIDED'])
    if wait_heartbeat(lambda m: m.custom_mode == modes['GUIDED'], 20) is None:
        raise RuntimeError('GUIDED not observed')
    link.arducopter_arm()
    armed = wait_heartbeat(lambda m: bool(m.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED), 70, True)
    result['checks']['armed'] = {'passed': armed is not None}
    if armed is None:
        raise RuntimeError('normal arming checks did not pass')
    link.set_mode(modes['AUTO'])
    auto = wait_heartbeat(lambda m: m.custom_mode == modes['AUTO'], 20)
    result['checks']['auto_mode'] = {'passed': auto is not None}
    if auto is None:
        raise RuntimeError('AUTO not observed')
    deadline, peak, disarmed = time.monotonic() + 180, 0.0, False
    while time.monotonic() < deadline:
        msg = link.recv_match(type=['HEARTBEAT', 'STATUSTEXT', 'MISSION_CURRENT',
                                    'MISSION_ITEM_REACHED', 'GLOBAL_POSITION_INT'], blocking=True, timeout=1)
        if not msg:
            continue
        kind = msg.get_type()
        if kind == 'STATUSTEXT':
            result['status_messages'].append(str(msg.text))
        elif kind == 'MISSION_CURRENT':
            if msg.seq not in result['mission_current']:
                result['mission_current'].append(msg.seq)
        elif kind == 'MISSION_ITEM_REACHED':
            if msg.seq not in result['mission_reached']:
                result['mission_reached'].append(msg.seq)
        elif kind == 'GLOBAL_POSITION_INT':
            peak = max(peak, msg.relative_alt / 1000.0)
        elif not (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED):
            disarmed = True
            break
    result['checks']['takeoff'] = {'passed': peak >= 3, 'peak_relative_alt_m': peak}
    result['checks']['mission_progress'] = {'passed': any(seq >= 2 for seq in result['mission_current']),
                                             'current_sequences': result['mission_current']}
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
    result['passed'] = not result['errors'] and len(result['checks']) == 7 and all(v['passed'] for v in result['checks'].values())
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
if not result['passed']:
    raise SystemExit(1)
