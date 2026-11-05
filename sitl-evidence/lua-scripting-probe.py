"""Run a benign repeating Lua status message in disposable local Copter SITL."""
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
run = base / os.environ.get('SITL_RUN_NAME', 'archive-lua-scripting')
run.mkdir(exist_ok=True)
output = run / 'results.json'
if output.exists():
    raise FileExistsError('refusing to overwrite prior evidence')
scripts = run / 'scripts'
scripts.mkdir(exist_ok=True)
script = scripts / 'codex_probe.lua'
script.write_text('local n = 0\nlocal function update()\n  n = n + 1\n  gcs:send_text(6, "CODEX_LUA_PROBE " .. n)\n  return update, 1000\nend\nreturn update, 1000\n')
scenario = os.environ.get('SITL_SCRIPT_SCENARIO', 'normal')
if scenario not in ('normal', 'instruction_limit', 'disabled_directory'):
    raise ValueError('unknown script scenario')
defaults = run / 'scripting.parm'
defaults.write_text('SCR_ENABLE 1\n' + ('SCR_DIR_DISABLE 2\n' if scenario == 'disabled_directory' else ''))
result = {'scope': 'Disposable source-built Copter SITL; benign script and standalone client; no physical aircraft',
          'scenario': scenario, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
          'script_sha256': hashlib.sha256(script.read_bytes()).hexdigest(), 'messages': [], 'status_text': [], 'errors': []}
if scenario == 'instruction_limit':
    limit_script = scripts / 'codex_limit.lua'
    limit_script.write_text('local function update()\n  while true do end\nend\nreturn update, 8000\n')
    result['limit_script_sha256'] = hashlib.sha256(limit_script.read_bytes()).hexdigest()
process = link = log = None
try:
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 6550))
    log = (run / 'sitl.log').open('wb')
    process = subprocess.Popen([str(binary), '-I', '79', '--model', 'quad', '--defaults', str(defaults),
                                '--home', '-35.363261,149.165230,584,0'], cwd=run,
                               stdout=log, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f'simulator exited: {process.returncode}')
        try:
            link = mavutil.mavlink_connection('tcp:127.0.0.1:6550', source_system=255)
            break
        except OSError:
            time.sleep(.5)
    if link is None or not link.wait_heartbeat(timeout=30):
        raise TimeoutError('no heartbeat')
    link.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0,
                            mavutil.mavlink.MAV_STATE_ACTIVE)
    link.mav.param_request_read_send(link.target_system, link.target_component, b'SCR_ENABLE', -1)
    if scenario == 'disabled_directory':
        link.mav.param_request_read_send(link.target_system, link.target_component, b'SCR_DIR_DISABLE', -1)
    observation_start = time.monotonic()
    deadline = observation_start + (15 if scenario == 'disabled_directory' else 35)
    next_heartbeat = 0
    while time.monotonic() < deadline:
        if time.monotonic() >= next_heartbeat:
            link.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0,
                                    mavutil.mavlink.MAV_STATE_ACTIVE)
            next_heartbeat = time.monotonic() + 1
        msg = link.recv_match(type=['STATUSTEXT', 'PARAM_VALUE'], blocking=True, timeout=1)
        if msg and msg.get_type() == 'STATUSTEXT':
            result['status_text'].append(msg.text)
            if 'CODEX_LUA_PROBE ' in msg.text:
                result['messages'].append(msg.text)
        if msg and msg.get_type() == 'PARAM_VALUE' and msg.param_id == 'SCR_ENABLE':
            result['scr_enable'] = msg.param_value
        if msg and msg.get_type() == 'PARAM_VALUE' and msg.param_id == 'SCR_DIR_DISABLE':
            result['scr_dir_disable'] = msg.param_value
        if scenario == 'normal' and len(result['messages']) >= 3:
            break
        if scenario == 'instruction_limit' and any('codex_limit.lua exceeded time limit' in text for text in result['status_text']):
            error_index = next(i for i, text in enumerate(result['status_text']) if 'codex_limit.lua exceeded time limit' in text)
            if any('CODEX_LUA_PROBE ' in text for text in result['status_text'][error_index + 1:]):
                break
    result['observation_seconds'] = time.monotonic() - observation_start
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
    if scenario == 'normal':
        result['passed'] = not result['errors'] and len(result['messages']) >= 3 and len(set(result['messages'])) >= 3
    elif scenario == 'instruction_limit':
        text = result['status_text']
        error_index = next((i for i, value in enumerate(text) if 'codex_limit.lua exceeded time limit' in value), None)
        result['passed'] = not result['errors'] and error_index is not None and any(
            'CODEX_LUA_PROBE ' in value for value in text[error_index + 1:])
    else:
        result['passed'] = (not result['errors'] and result.get('scr_enable') == 1 and
                            result.get('scr_dir_disable') == 2 and not result['messages'] and
                            result.get('observation_seconds', 0) >= 15)
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
if not result['passed']:
    raise SystemExit(1)
