"""Reboot a copy of calibrated SITL storage and compare emitted saved values."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink import mavutil
from pymavlink.dialects.v20 import ardupilotmega
original = root / 'sitl-evidence/command-ack-calibration_full'
out = root / 'sitl-evidence/accel-calibration-reboot'
out.mkdir(exist_ok=False)
binary = root / 'sitl-evidence/archive-built/arducopter'
source_storage = original / 'eeprom.bin'
shutil.copyfile(source_storage, out / 'eeprom.bin')
shutil.copyfile(source_storage, out / 'eeprom-before.bin')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
names = ['INS_ACC_ID', 'INS_ACC2_ID'] + ['INS_' + prefix + axis for prefix in
         ('ACCOFFS_', 'ACCSCAL_', 'ACC2OFFS_', 'ACC2SCAL_') for axis in ('X', 'Y', 'Z')]
parser = ardupilotmega.MAVLink(None); parser.robust_parsing = True
after_six = False; expected = {}; success = False
for b in (original / 'to_client_output.bin').read_bytes():
    msg = parser.parse_char(bytes([b]))
    if msg is None: continue
    if msg.get_type() == 'COMMAND_LONG' and msg.command == 42429 and msg.param1 == 6: after_six = True
    elif after_six and msg.get_type() == 'PARAM_VALUE' and msg.param_id in names: expected[msg.param_id] = msg.param_value
    elif after_six and msg.get_type() == 'STATUSTEXT' and 'Calibration successful' in msg.text: success = True; break
assert success and set(expected) == set(names)
log = (out / 'sitl.log').open('wb')
proc = None; connection = None
result = {'expected_from_prior_capture': expected, 'errors': [], 'observed_after_reboot': {},
          'binary_sha256': sha(binary), 'original_capture_sha256': sha(original / 'to_client_output.bin'),
          'source_storage_sha256': sha(source_storage), 'copied_storage_sha256': sha(out / 'eeprom.bin')}
try:
    assert result['source_storage_sha256'] == result['copied_storage_sha256']
    proc = subprocess.Popen([str(binary), '-I', '150', '--model', 'calibration',
                             '--home=-35.363261,149.165230,584,0'], cwd=out, stdout=log, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 35
    while True:
        if proc.poll() is not None: raise RuntimeError('SITL exited before connection')
        try:
            connection = mavutil.mavlink_connection('tcp:127.0.0.1:7260', source_system=255, source_component=190)
            break
        except OSError:
            if time.monotonic() > deadline: raise
            time.sleep(0.3)
    raw = (out / 'downlink.bin').open('wb'); connection.logfile_raw = raw
    heartbeat = connection.wait_heartbeat(timeout=15)
    if heartbeat is None or (heartbeat.base_mode & 128): raise RuntimeError('no disarmed heartbeat')
    result['initial_heartbeat'] = heartbeat.to_dict()
    for name in names:
        value = None
        for attempt in range(3):
            connection.mav.param_request_read_send(1, 1, name.encode('ascii'), -1)
            until = time.monotonic() + 4
            while time.monotonic() < until:
                msg = connection.recv_match(type='PARAM_VALUE', blocking=True, timeout=0.5)
                if msg is not None and msg.get_srcSystem() == 1 and msg.get_srcComponent() == 1 and msg.param_id == name:
                    value = msg.param_value; break
            if value is not None: break
        if value is None: raise RuntimeError('parameter timeout ' + name)
        result['observed_after_reboot'][name] = value
    if result['observed_after_reboot'] != expected: raise RuntimeError('readback differs from calibration output')
except Exception as exc:
    result['errors'].append(repr(exc))
    raise
finally:
    if connection is not None: connection.close()
    if 'raw' in locals(): raw.close()
    if proc is not None:
        proc.terminate()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)
    log.close()
    result['post_shutdown_storage_sha256'] = sha(out / 'eeprom.bin')
    result['downlink_sha256'] = sha(out / 'downlink.bin') if (out / 'downlink.bin').exists() else None
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print('Compared', len(names), 'calibration values after reboot; all matched')
