"""Leave and re-enter Auto with mission restart enabled in disposable Copter SITL."""
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
run = base / 'archive-copter-mission-restart'
run.mkdir(exist_ok=True)
output = run / 'results.json'
if output.exists():
    raise FileExistsError('refusing to overwrite prior results')
port = 6860
result = {'scope': 'Disposable source-built Copter SITL; standalone MAVLink client; no physical aircraft',
          'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
          'checks': {}, 'status_messages': [], 'mission_current': [], 'mission_reached': [], 'events': [], 'errors': []}
process = link = log = None
started = time.monotonic()

def wait_heartbeat(predicate, seconds, retry_arm=False):
    deadline, retry = time.monotonic() + seconds, time.monotonic() + 8
    while time.monotonic() < deadline:
        if retry_arm and time.monotonic() >= retry:
            link.arducopter_arm()
            retry = time.monotonic() + 8
        msg = link.recv_match(type=['HEARTBEAT', 'STATUSTEXT'], blocking=True, timeout=1)
        if msg and msg.get_type() == 'STATUSTEXT':
            result['status_messages'].append(str(msg.text))
            result['events'].append({'seconds': round(time.monotonic() - started, 3), 'type': 'STATUSTEXT', 'text': str(msg.text)})
        elif msg and predicate(msg):
            return msg
    return None

try:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', port))
    log = (run / 'sitl.log').open('wb')
    process = subprocess.Popen([str(binary), '-I', '110', '--model', 'quad',
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
    link.mav.param_set_send(system, component, b'MIS_RESTART', 1, mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
    deadline, resume_setting = time.monotonic() + 15, None
    while time.monotonic() < deadline:
        msg = link.recv_match(type='PARAM_VALUE', blocking=True, timeout=1)
        if msg and str(msg.param_id).rstrip('\x00') == 'MIS_RESTART':
            resume_setting = msg.param_value
            break
    result['checks']['resume_option'] = {'passed': resume_setting == 1, 'value': resume_setting}
    if resume_setting != 1:
        raise RuntimeError('MIS_RESTART restart setting not confirmed')
    # Home, takeoff, nearby waypoint, land. Coordinates are simulation only.
    lat, lon = -353632610, 1491652300
    items = [(mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, lat, lon, 0),
             (mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, lat, lon, 5),
             (mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, lat + 6000, lon, 5),
             (mavutil.mavlink.MAV_CMD_NAV_LAND, lat + 6000, lon, 0)]
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
    # Confirm flight altitude and selection of the distant waypoint before changing to BRAKE.
    deadline, waypoint_selected, altitude_before = time.monotonic() + 90, False, 0.0
    while time.monotonic() < deadline:
        msg = link.recv_match(type=['MISSION_CURRENT', 'STATUSTEXT', 'GLOBAL_POSITION_INT'], blocking=True, timeout=1)
        if not msg:
            continue
        if msg.get_type() == 'STATUSTEXT':
            result['status_messages'].append(str(msg.text))
        elif msg.get_type() == 'MISSION_CURRENT':
            result['events'].append({'seconds': round(time.monotonic() - started, 3), 'type': 'MISSION_CURRENT', 'seq': msg.seq, 'phase': 'before_pause'})
            if msg.seq == 2:
                waypoint_selected = True
        elif msg.get_type() == 'GLOBAL_POSITION_INT':
            altitude_before = msg.relative_alt / 1000.0
        if waypoint_selected and altitude_before >= 3:
            break
    result['checks']['waypoint_selected'] = {'passed': waypoint_selected and altitude_before >= 3,
                                             'seq': 2, 'relative_alt_m': altitude_before}
    if not result['checks']['waypoint_selected']['passed']:
        raise RuntimeError('waypoint sequence 2 or flight altitude not observed')
    link.set_mode(modes['BRAKE'])
    brake = wait_heartbeat(lambda m: m.custom_mode == modes['BRAKE'], 20)
    result['events'].append({'seconds': round(time.monotonic() - started, 3), 'type': 'BRAKE_observed', 'observed': brake is not None})
    result['checks']['pause_mode'] = {'passed': brake is not None, 'mode': modes['BRAKE']}
    if brake is None:
        raise RuntimeError('BRAKE not observed')
    deadline, paused_sequences, paused_altitudes = time.monotonic() + 5, [], []
    while time.monotonic() < deadline:
        msg = link.recv_match(type=['MISSION_CURRENT', 'HEARTBEAT', 'STATUSTEXT', 'GLOBAL_POSITION_INT'], blocking=True, timeout=1)
        if msg and msg.get_type() == 'MISSION_CURRENT':
            paused_sequences.append(msg.seq)
            result['events'].append({'seconds': round(time.monotonic() - started, 3), 'type': 'MISSION_CURRENT', 'seq': msg.seq, 'phase': 'pause'})
        elif msg and msg.get_type() == 'STATUSTEXT':
            result['status_messages'].append(str(msg.text))
        elif msg and msg.get_type() == 'GLOBAL_POSITION_INT':
            paused_altitudes.append(msg.relative_alt / 1000.0)
    result['checks']['paused_sequence'] = {'passed': bool(paused_sequences) and all(seq == 2 for seq in paused_sequences),
                                            'sequences': paused_sequences, 'altitude_samples_m': paused_altitudes}
    result['events'].append({'seconds': round(time.monotonic() - started, 3), 'type': 'AUTO_restart_requested'})
    link.set_mode(modes['AUTO'])
    resumed = wait_heartbeat(lambda m: m.custom_mode == modes['AUTO'], 20)
    result['events'].append({'seconds': round(time.monotonic() - started, 3), 'type': 'AUTO_resumed', 'observed': resumed is not None})
    result['checks']['resumed_mode'] = {'passed': resumed is not None}
    if resumed is None:
        raise RuntimeError('resumed AUTO not observed')
    deadline, peak, disarmed = time.monotonic() + 180, 0.0, False
    while time.monotonic() < deadline:
        msg = link.recv_match(type=['HEARTBEAT', 'STATUSTEXT', 'MISSION_CURRENT',
                                    'MISSION_ITEM_REACHED', 'GLOBAL_POSITION_INT'], blocking=True, timeout=1)
        if not msg:
            continue
        kind = msg.get_type()
        if kind == 'STATUSTEXT':
            result['status_messages'].append(str(msg.text))
            result['events'].append({'seconds': round(time.monotonic() - started, 3), 'type': 'STATUSTEXT', 'text': str(msg.text)})
        elif kind == 'MISSION_CURRENT':
            result['events'].append({'seconds': round(time.monotonic() - started, 3), 'type': 'MISSION_CURRENT', 'seq': msg.seq, 'phase': 'after_resume'})
            if msg.seq not in result['mission_current']:
                result['mission_current'].append(msg.seq)
        elif kind == 'MISSION_ITEM_REACHED':
            result['events'].append({'seconds': round(time.monotonic() - started, 3), 'type': 'MISSION_ITEM_REACHED', 'seq': msg.seq, 'phase': 'after_resume'})
            if msg.seq not in result['mission_reached']:
                result['mission_reached'].append(msg.seq)
        elif kind == 'GLOBAL_POSITION_INT':
            peak = max(peak, msg.relative_alt / 1000.0)
        elif not (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED):
            disarmed = True
            break
    result['checks']['takeoff'] = {'passed': peak >= 3, 'peak_relative_alt_m': peak}
    result['checks']['mission_progress'] = {'passed': 2 in result['mission_current'] and 3 in result['mission_current'] and 2 in result['mission_reached'],
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
    result['passed'] = not result['errors'] and len(result['checks']) == 12 and all(v['passed'] for v in result['checks'].values())
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
if not result['passed']:
    raise SystemExit(1)
