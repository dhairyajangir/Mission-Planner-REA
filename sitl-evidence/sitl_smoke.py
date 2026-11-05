"""Bounded, read-only MAVLink checks against an isolated ArduCopter SITL process."""
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
from pymavlink import mavutil

BINARY = Path(os.environ.get('SITL_BINARY', str(BASE / 'arducopter'))).resolve()
RUN_NAME = os.environ.get('SITL_RUN_NAME', 'smoke-run-2')
if Path(RUN_NAME).name != RUN_NAME:
    raise ValueError('SITL_RUN_NAME must be a single directory name')
RUN = BASE / RUN_NAME
RUN.mkdir(exist_ok=True)
if (RUN / 'results.json').exists():
    raise FileExistsError('refusing to overwrite previous test results')
INSTANCE = int(os.environ.get('SITL_INSTANCE', '38'))
PORT = 5760 + INSTANCE * 10
MODEL = os.environ.get('SITL_MODEL', 'quad')
PARAMETER = os.environ.get('SITL_PARAMETER', 'FRAME_CLASS')
result = {'scope': 'ArduPilot SITL, MAVLink client; Mission Planner not exercised',
          'binary': str(BINARY), 'binary_sha256': hashlib.sha256(BINARY.read_bytes()).hexdigest(),
          'model': MODEL,
          'checks': {}, 'errors': [], 'port': PORT}
proc = None
link = None
try:
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', PORT))
    log = (RUN / 'sitl.log').open('wb')
    proc = subprocess.Popen([str(BINARY), '-I', str(INSTANCE), '--model', MODEL,
                             '--home', '-35.363261,149.165230,584,0'],
                            cwd=RUN, stdout=log, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f'SITL exited before connection: {proc.returncode}')
        try:
            link = mavutil.mavlink_connection(f'tcp:127.0.0.1:{PORT}', source_system=255)
            break
        except OSError:
            time.sleep(0.5)
    if link is None:
        raise TimeoutError('SITL TCP listener not available')
    hb = link.wait_heartbeat(timeout=30)
    if hb is None:
        raise TimeoutError('No heartbeat')
    result['checks']['heartbeat'] = {'passed': True, 'system': link.target_system,
                                     'component': link.target_component, 'type': hb.type,
                                     'autopilot': hb.autopilot}
    link.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,
                            mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0,
                            mavutil.mavlink.MAV_STATE_ACTIVE)
    link.mav.request_data_stream_send(link.target_system, link.target_component,
                                      mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1)
    pending = {'ATTITUDE', 'GLOBAL_POSITION_INT', 'SYS_STATUS'}
    end = time.monotonic() + 25
    while pending and time.monotonic() < end:
        msg = link.recv_match(type=list(pending), blocking=True, timeout=1)
        if msg:
            pending.discard(msg.get_type())
    for kind in ('ATTITUDE', 'GLOBAL_POSITION_INT', 'SYS_STATUS'):
        result['checks'][kind] = {'passed': kind not in pending}
    link.mav.param_request_read_send(link.target_system, link.target_component, PARAMETER.encode('ascii'), -1)
    end = time.monotonic() + 15
    param = None
    while time.monotonic() < end:
        msg = link.recv_match(type='PARAM_VALUE', blocking=True, timeout=1)
        if msg and str(msg.param_id).rstrip('\x00') == PARAMETER:
            param = msg
            break
    result['checks']['parameter_read'] = {'passed': param is not None,
                                           'name': PARAMETER,
                                           'value': param.param_value if param else None}
    link.mav.mission_request_list_send(link.target_system, link.target_component)
    count = link.recv_match(type='MISSION_COUNT', blocking=True, timeout=15)
    result['checks']['mission_list'] = {'passed': count is not None,
                                        'count': count.count if count else None}
except Exception:
    result['errors'].append(traceback.format_exc())
finally:
    if link is not None:
        link.close()
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
    if proc is not None:
        result['process_exit_code'] = proc.returncode
        log.close()
    result['passed'] = not result['errors'] and bool(result['checks']) and all(
        c['passed'] for c in result['checks'].values())
    (RUN / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
sys.exit(0 if result['passed'] else 1)
