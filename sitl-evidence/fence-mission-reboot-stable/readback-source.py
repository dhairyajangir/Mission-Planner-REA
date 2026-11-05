"""Read mission and fence after rebooting a copy of disposable SITL storage."""
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
source = root / 'sitl-evidence/command-ack-fence_roundtrip_stable'
out = root / 'sitl-evidence/fence-mission-reboot-stable'
out.mkdir(exist_ok=False)
storage = source / 'eeprom.bin'
shutil.copyfile(storage, out / 'eeprom.bin'); shutil.copyfile(storage, out / 'eeprom-before.bin')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
binary = root / 'sitl-evidence/archive-built/arducopter'
original = json.loads((source / 'summary.json').read_text())
fields = ('seq', 'command', 'param1', 'param2', 'param3', 'param4', 'x', 'y', 'z', 'mission_type')
expected = {}
for typ, count in ((0, 2), (1, 4)):
    items = [m for m in original['received'] if m['mission_type'] == typ][:count]
    assert len(items) == count
    expected[str(typ)] = [{k: m[k] for k in fields} for m in items]
result = {'scope': 'Copter SITL reboot from a copy of mission/fence run storage; standalone MAVLink client',
          'binary_sha256': sha(binary), 'source_storage_sha256': sha(storage), 'copied_storage_sha256': sha(out / 'eeprom.bin'),
          'source_summary_sha256': sha(source / 'summary.json'), 'expected': expected, 'observed': {}, 'errors': []}
proc = connection = raw = None
log = (out / 'sitl.log').open('wb')
try:
    assert result['source_storage_sha256'] == result['copied_storage_sha256']
    proc = subprocess.Popen([str(binary), '-I', '172', '--model', 'quad', '--home=-35.363261,149.165230,584,0'], cwd=out,
                            stdout=log, stderr=subprocess.STDOUT)
    until = time.monotonic() + 35
    while True:
        if proc.poll() is not None: raise RuntimeError('simulator exited')
        try:
            connection = mavutil.mavlink_connection('tcp:127.0.0.1:7480', source_system=255, source_component=190)
            break
        except OSError:
            if time.monotonic() >= until: raise
            time.sleep(0.3)
    raw = (out / 'downlink.bin').open('wb'); connection.logfile_raw = raw
    heartbeat = connection.wait_heartbeat(timeout=15)
    if heartbeat is None or heartbeat.base_mode & 128: raise RuntimeError('no disarmed heartbeat')
    result['initial_heartbeat'] = heartbeat.to_dict()
    until = time.monotonic() + 12
    while time.monotonic() < until:
        connection.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
        connection.recv_match(blocking=True, timeout=1)
    result['startup_wait_seconds'] = 12
    for typ, count in ((0, 2), (1, 4)):
        connection.mav.mission_request_list_send(1, 1, typ)
        until = time.monotonic() + 12
        response = None
        while time.monotonic() < until:
            msg = connection.recv_match(type='MISSION_COUNT', blocking=True, timeout=1)
            if msg is not None and msg.get_srcSystem() == 1 and msg.mission_type == typ:
                response = msg; break
        if response is None or response.count != count: raise RuntimeError('unexpected count for ' + str(typ))
        rows = []
        for i in range(count):
            connection.mav.mission_request_int_send(1, 1, i, typ)
            until = time.monotonic() + 12
            item = None
            while time.monotonic() < until:
                msg = connection.recv_match(type='MISSION_ITEM_INT', blocking=True, timeout=1)
                if msg is not None and msg.get_srcSystem() == 1 and msg.mission_type == typ and msg.seq == i:
                    item = msg; break
            if item is None: raise RuntimeError('missing item ' + str((typ, i)))
            data = item.to_dict(); rows.append({k: data[k] for k in fields})
        result['observed'][str(typ)] = rows
        if rows != expected[str(typ)]: raise RuntimeError('readback mismatch ' + str(typ))
        connection.mav.mission_ack_send(1, 1, mavutil.mavlink.MAV_MISSION_ACCEPTED, typ)
except Exception as exc:
    result['errors'].append(repr(exc)); raise
finally:
    if connection is not None: connection.close()
    if raw is not None: raw.close()
    if proc is not None:
        proc.terminate()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)
    log.close()
    result['post_shutdown_storage_sha256'] = sha(out / 'eeprom.bin')
    result['downlink_sha256'] = sha(out / 'downlink.bin') if (out / 'downlink.bin').exists() else None
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print('Reboot readback matched', sum(len(v) for v in expected.values()), 'mission and fence items')
