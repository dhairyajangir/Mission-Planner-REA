"""Compare rejected fence and rally replacement uploads on disposable Copter SITL."""
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
run = base / 'archive-fence-rally-rejection'
run.mkdir(exist_ok=True)
output = run / 'results.json'
if output.exists():
    raise FileExistsError('refusing to overwrite prior evidence')
result = {'scope': 'Disposable source-built Copter SITL; standalone MAVLink 2 client; no physical aircraft',
          'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'checks': {}, 'errors': []}
process = link = log = None


def receive(types, mission_type, timeout=20):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        msg = link.recv_match(type=types, blocking=True, timeout=1)
        if msg and getattr(msg, 'mission_type', None) == mission_type:
            return msg
    raise TimeoutError(f'no {types} for mission type {mission_type}')


def upload(kind, items, invalid=False):
    link.mav.mission_count_send(link.target_system, link.target_component, len(items), kind)
    requests = []
    while True:
        msg = receive(['MISSION_REQUEST_INT', 'MISSION_REQUEST', 'MISSION_ACK'], kind)
        if msg.get_type() == 'MISSION_ACK':
            return {'requests': requests, 'ack': msg.type,
                    'ack_name': mavutil.mavlink.enums['MAV_MISSION_RESULT'][msg.type].name}
        if msg.seq >= len(items):
            raise ValueError(f'unexpected item request {msg.seq}')
        requests.append(msg.seq)
        item = items[msg.seq]
        frame = 255 if invalid and msg.seq == 1 else mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT
        lat = item['lat'] + (5000 if invalid and msg.seq == 0 else 0)
        link.mav.mission_item_int_send(link.target_system, link.target_component, msg.seq, frame,
                                       item['command'], 0, 1, item['param1'], 0, 0, 0,
                                       lat, item['lon'], item['alt'], kind)


def read_all(kind):
    link.mav.mission_request_list_send(link.target_system, link.target_component, kind)
    count = receive(['MISSION_COUNT'], kind).count
    items = []
    for seq in range(count):
        link.mav.mission_request_int_send(link.target_system, link.target_component, seq, kind)
        msg = receive(['MISSION_ITEM_INT', 'MISSION_ACK'], kind)
        if msg.get_type() != 'MISSION_ITEM_INT' or msg.seq != seq:
            raise RuntimeError(f'unexpected read response: {msg}')
        items.append({'seq': seq, 'lat': msg.x, 'lon': msg.y, 'alt': msg.z,
                      'command': msg.command, 'param1': msg.param1})
    link.mav.mission_ack_send(link.target_system, link.target_component,
                              mavutil.mavlink.MAV_MISSION_ACCEPTED, kind)
    return items


try:
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 6540))
    log = (run / 'sitl.log').open('wb')
    process = subprocess.Popen([str(binary), '-I', '78', '--model', 'quad',
                                '--home', '-35.363261,149.165230,584,0'], cwd=run,
                               stdout=log, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f'simulator exited: {process.returncode}')
        try:
            link = mavutil.mavlink_connection('tcp:127.0.0.1:6540', source_system=255)
            break
        except OSError:
            time.sleep(.5)
    if link is None or not link.wait_heartbeat(timeout=30):
        raise TimeoutError('no heartbeat')
    time.sleep(20)
    for name, kind, command, param1 in (
            ('fence', mavutil.mavlink.MAV_MISSION_TYPE_FENCE, mavutil.mavlink.MAV_CMD_NAV_FENCE_CIRCLE_INCLUSION, 100),
            ('rally', mavutil.mavlink.MAV_MISSION_TYPE_RALLY, mavutil.mavlink.MAV_CMD_NAV_RALLY_POINT, 0)):
        items = [{'lat': -353632610 + 10000 * i, 'lon': 1491652300 + 10000 * i,
                  'alt': 20, 'command': command, 'param1': param1} for i in range(2)]
        baseline_upload = upload(kind, items)
        baseline = read_all(kind)
        established = baseline_upload['ack'] == 0 and len(baseline) == 2 and baseline[0]['lat'] == items[0]['lat']
        result['checks'][name + '_baseline'] = {'passed': established, 'upload': baseline_upload, 'readback': baseline}
        if not established:
            raise RuntimeError(f'{name} baseline was not established')
        replacement = upload(kind, items, invalid=True)
        after = read_all(kind)
        result['checks'][name + '_rejection'] = {'passed': replacement['ack'] != 0,
                                                 'upload': replacement, 'readback': after}
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
    result['passed'] = not result['errors'] and len(result['checks']) == 4 and all(v['passed'] for v in result['checks'].values())
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
if not result['passed']:
    raise SystemExit(1)
