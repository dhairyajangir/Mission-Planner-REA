"""Test non-finite parameter writes only in a disposable local Copter SITL."""
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import traceback

os.environ['MAVLINK20'] = '1'
base = Path(__file__).resolve().parent
sys.path.insert(0, str(base / 'python'))
from pymavlink import mavutil

binary = base / 'archive-built/arducopter'
run = base / 'archive-copter-nonfinite-param'
run.mkdir(exist_ok=True)
output = run / 'results.json'
if output.exists():
    raise FileExistsError('refusing to overwrite prior results')
port = 6890
result = {'scope': 'Disposable source-built Copter SITL; standalone MAVLink 2 client; no physical aircraft',
          'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'checks': {}, 'exchanges': [], 'errors': []}
process = link = log = None
name = 'LOG_DISARMED'

def receive_window(seconds):
    deadline, replies = time.monotonic() + seconds, []
    while time.monotonic() < deadline:
        msg = link.recv_match(type=['PARAM_VALUE', 'PARAM_ERROR', 'STATUSTEXT'], blocking=True, timeout=.3)
        if not msg:
            continue
        if msg.get_type() == 'STATUSTEXT':
            replies.append({'type': 'STATUSTEXT', 'text': str(msg.text)})
        elif str(msg.param_id).rstrip('\x00') == name:
            row = {'type': msg.get_type(), 'name': str(msg.param_id).rstrip('\x00')}
            if msg.get_type() == 'PARAM_ERROR':
                row['error'] = msg.error
            else:
                row['value'] = msg.param_value
            replies.append(row)
    return replies

def read_param():
    link.mav.param_request_read_send(link.target_system, link.target_component, name.encode('ascii'), -1)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        msg = link.recv_match(type='PARAM_VALUE', blocking=True, timeout=.5)
        if msg and str(msg.param_id).rstrip('\x00') == name:
            return msg.param_value
    raise TimeoutError('parameter read did not return')

def write_param(value):
    link.mav.param_set_send(link.target_system, link.target_component, name.encode('ascii'), value,
                            mavutil.mavlink.MAV_PARAM_TYPE_REAL32)

try:
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', port))
    log = (run / 'sitl.log').open('wb')
    process = subprocess.Popen([str(binary), '-I', '113', '--model', 'quad',
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
    link.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID,
                            0, 0, mavutil.mavlink.MAV_STATE_ACTIVE)
    baseline = read_param()
    result['checks']['baseline'] = {'passed': baseline == 0, 'value': baseline}
    if baseline != 0:
        raise RuntimeError('fresh simulator baseline was not zero')
    for label, value in [('nan', math.nan), ('positive_infinity', math.inf), ('negative_infinity', -math.inf)]:
        write_param(value)
        replies = receive_window(3)
        after = read_param()
        error_seen = any(row.get('type') == 'PARAM_ERROR' and row.get('error') == 2 for row in replies)
        result['exchanges'].append({'sent': label, 'replies': replies, 'readback': after})
        result['checks'][label] = {'passed': error_seen and after == baseline,
                                   'out_of_range_error_seen': error_seen, 'readback': after}
    write_param(1)
    finite_replies = receive_window(2)
    changed = read_param()
    result['exchanges'].append({'sent': 'finite_one', 'replies': finite_replies, 'readback': changed})
    result['checks']['finite_control'] = {'passed': changed == 1, 'readback': changed}
    write_param(0)
    reset_replies = receive_window(2)
    restored = read_param()
    result['exchanges'].append({'sent': 'restore_zero', 'replies': reset_replies, 'readback': restored})
    result['checks']['restored'] = {'passed': restored == 0, 'readback': restored}
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
