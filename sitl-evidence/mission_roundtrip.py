"""Upload and download a small mission on an isolated local SITL instance."""
import json
import hashlib
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import traceback

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / 'python'))
os.environ['MAVLINK20'] = '1'
from pymavlink import mavutil

BINARY = Path(os.environ.get('SITL_BINARY', str(BASE / 'arducopter'))).resolve()
RUN_NAME = os.environ.get('SITL_RUN_NAME', 'mission-roundtrip-4')
if Path(RUN_NAME).name != RUN_NAME:
    raise ValueError('SITL_RUN_NAME must be a single directory name')
RUN = BASE / RUN_NAME
RUN.mkdir(exist_ok=True)
if (RUN / 'results.json').exists():
    raise FileExistsError('refusing to overwrite previous test results')
INSTANCE = int(os.environ.get('SITL_INSTANCE', '39'))
PORT = 5760 + INSTANCE * 10
result = {'scope': 'ArduCopter SITL only; no Mission Planner or aircraft',
          'binary': str(BINARY), 'binary_sha256': hashlib.sha256(BINARY.read_bytes()).hexdigest(),
          'checks': {}, 'errors': [], 'port': PORT}
proc = link = log = None
try:
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', PORT))
    log = (RUN / 'sitl.log').open('wb')
    proc = subprocess.Popen([str(BINARY), '-I', str(INSTANCE), '--model', 'quad',
                             '--home', '-35.363261,149.165230,584,0'],
                            cwd=RUN, stdout=log, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f'SITL exited: {proc.returncode}')
        try:
            link = mavutil.mavlink_connection(f'tcp:127.0.0.1:{PORT}', source_system=255)
            break
        except OSError:
            time.sleep(.5)
    if link is None or link.wait_heartbeat(timeout=30) is None:
        raise TimeoutError('No simulator heartbeat')
    system, component = link.target_system, link.target_component
    link.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,
                            mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0,
                            mavutil.mavlink.MAV_STATE_ACTIVE)
    # The first heartbeat can precede storage initialization. Allow SITL to
    # finish startup before requesting mission storage.
    time.sleep(15)
    items = [(-353632610, 1491652300, 0.0), (-353630000, 1491655000, 20.0)]
    link.mav.mission_count_send(system, component, len(items))
    sent = set()
    request_types = []
    ack = None
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        msg = link.recv_match(type=['MISSION_REQUEST_INT', 'MISSION_REQUEST', 'MISSION_ACK'],
                              blocking=True, timeout=1)
        if msg is None:
            continue
        if msg.get_type() == 'MISSION_ACK':
            ack = msg
            break
        seq = msg.seq
        request_types.append(msg.get_type())
        if seq >= len(items):
            raise ValueError(f'unexpected request sequence {seq}')
        lat, lon, alt = items[seq]
        args = (system, component, seq, mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, 0, 1, 0, 0, 0, 0)
        # Probe whether SITL accepts the integer item even if its request is
        # legacy MISSION_REQUEST. Record the request types in the evidence.
        link.mav.mission_item_int_send(*args, lat, lon, alt)
        sent.add(seq)
    result['checks']['mission_upload'] = {'passed': ack is not None and ack.type == 0 and sent == {0, 1},
                                          'sent_sequences': sorted(sent), 'request_types': request_types,
                                          'ack': ack.type if ack else None}
    link.mav.mission_request_list_send(system, component)
    count = link.recv_match(type='MISSION_COUNT', blocking=True, timeout=15)
    result['checks']['mission_count'] = {'passed': count is not None and count.count == 2,
                                         'count': count.count if count else None}
    link.mav.mission_request_int_send(system, component, 1)
    item = link.recv_match(type='MISSION_ITEM_INT', blocking=True, timeout=15)
    result['checks']['waypoint_readback'] = {'passed': item is not None and item.seq == 1 and
                                             item.x == items[1][0] and item.y == items[1][1] and
                                             abs(item.z - items[1][2]) < .01,
                                             'sequence': item.seq if item else None,
                                             'lat_e7': item.x if item else None,
                                             'lon_e7': item.y if item else None,
                                             'alt': item.z if item else None}
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
    if proc:
        result['process_exit_code'] = proc.returncode
    if log:
        log.close()
    result['passed'] = not result['errors'] and bool(result['checks']) and all(
        c['passed'] for c in result['checks'].values())
    (RUN / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
sys.exit(0 if result['passed'] else 1)
