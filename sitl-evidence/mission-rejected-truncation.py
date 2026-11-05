"""Probe an invalid mission frame and subsequent readback in local SITL."""
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
os.environ['MAVLINK20'] = '1'
from pymavlink import mavutil

binary = base / 'archive-built/arducopter'
run = base / 'archive-mission-rejected-truncation'
run.mkdir(exist_ok=True)
output = run / 'results.json'
if output.exists():
    raise FileExistsError('refusing to overwrite prior test evidence')
port = 6530
result = {'scope': 'Disposable source-built Copter SITL; standalone MAVLink client, no physical aircraft',
          'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'checks': {}, 'errors': []}
process = link = log = None
baseline = [(-353632610, 1491652300, 0.0), (-353630000, 1491655000, 20.0), (-353629000, 1491656000, 30.0), (-353628000, 1491657000, 40.0)]

def upload(invalid_frame):
    link.mav.mission_count_send(link.target_system, link.target_component, len(baseline) - 1 if invalid_frame else len(baseline))
    requests, ack = [], None
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        msg = link.recv_match(type=['MISSION_REQUEST_INT', 'MISSION_REQUEST', 'MISSION_ACK'], blocking=True, timeout=1)
        if not msg:
            continue
        if msg.get_type() == 'MISSION_ACK':
            ack = msg.type
            break
        if msg.seq >= len(baseline):
            raise ValueError(f'unexpected sequence {msg.seq}')
        requests.append(msg.seq)
        lat, lon, altitude = baseline[msg.seq]
        if invalid_frame and msg.seq == 1:
            altitude = 25.0
        frame = 255 if invalid_frame and msg.seq == 2 else mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT
        link.mav.mission_item_int_send(link.target_system, link.target_component, msg.seq, frame,
                                       mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, 0, 1, 0, 0, 0, 0,
                                       lat, lon, altitude)
    return {'request_sequences': requests, 'ack': ack,
            'ack_name': mavutil.mavlink.enums['MAV_MISSION_RESULT'][ack].name if ack in mavutil.mavlink.enums['MAV_MISSION_RESULT'] else None}

def read_waypoint():
    link.mav.mission_request_list_send(link.target_system, link.target_component)
    count = link.recv_match(type='MISSION_COUNT', blocking=True, timeout=15)
    if not count:
        return {'count': None}
    link.mav.mission_request_int_send(link.target_system, link.target_component, 1)
    item = link.recv_match(type=['MISSION_ITEM_INT', 'MISSION_ACK'], blocking=True, timeout=15)
    if not item or item.get_type() != 'MISSION_ITEM_INT':
        return {'count': count.count, 'item_type': item.get_type() if item else None,
                'ack': item.type if item and item.get_type() == 'MISSION_ACK' else None}
    link.mav.mission_ack_send(link.target_system, link.target_component, mavutil.mavlink.MAV_MISSION_ACCEPTED)
    return {'count': count.count, 'seq': item.seq, 'lat_e7': item.x, 'lon_e7': item.y, 'alt_m': item.z}

try:
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', port))
    log = (run / 'sitl.log').open('wb')
    process = subprocess.Popen([str(binary), '-I', '77', '--model', 'quad',
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
    time.sleep(20)
    first = upload(False)
    before = read_waypoint()
    result['checks']['baseline'] = {'passed': first['ack'] == 0 and before.get('count') == 4 and
                                    before.get('lat_e7') == baseline[1][0] and before.get('lon_e7') == baseline[1][1],
                                    'upload': first, 'readback': before}
    if not result['checks']['baseline']['passed']:
        raise RuntimeError('baseline mission was not established')
    invalid = upload(True)
    after = read_waypoint()
    result['checks']['invalid_rejected'] = {'passed': invalid['ack'] is not None and invalid['ack'] != 0,
                                            'upload': invalid}
    result['post_rejection_readback'] = after
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
    result['passed'] = not result['errors'] and len(result['checks']) == 2 and all(v['passed'] for v in result['checks'].values())
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
if not result['passed']:
    raise SystemExit(1)
