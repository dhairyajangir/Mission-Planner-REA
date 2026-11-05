"""Read one parameter via a second local SITL serial endpoint, without changing it."""
import json
import os
from pathlib import Path
import sys
import time
import traceback

base = Path(__file__).resolve().parent
sys.path.insert(0, str(base / 'python'))
os.environ['MAVLINK20'] = '1'
from pymavlink import mavutil

run = base / 'integrated-ui-params-write'
output_name = os.environ.get('MP_READBACK_OUTPUT', 'independent-readback.json')
if Path(output_name).name != output_name:
    raise ValueError('readback output must be a filename')
out = run / output_name
expected = float(os.environ.get('MP_READBACK_EXPECTED', '1'))
if out.exists():
    raise FileExistsError('refusing to overwrite prior readback')
result = {'scope': 'read-only standalone MAVLink client via SITL secondary TCP serial endpoint',
          'target': '127.0.0.1:6582', 'parameter': 'LOG_DISARMED', 'errors': []}
link = None
try:
    link = mavutil.mavlink_connection('tcp:127.0.0.1:6582', source_system=254)
    link.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID,
                            0, 0, mavutil.mavlink.MAV_STATE_ACTIVE)
    deadline = time.monotonic() + 25
    next_request = 0
    while time.monotonic() < deadline:
        if time.monotonic() >= next_request:
            link.mav.param_request_read_send(1, 1, b'LOG_DISARMED', -1)
            next_request = time.monotonic() + 2
        msg = link.recv_match(type='PARAM_VALUE', blocking=True, timeout=1)
        if msg and msg.param_id == 'LOG_DISARMED':
            result['value'] = msg.param_value
            result['system'] = msg.get_srcSystem()
            result['component'] = msg.get_srcComponent()
            break
    if 'value' not in result:
        raise TimeoutError('no matching parameter response')
except Exception:
    result['errors'].append(traceback.format_exc())
finally:
    if link:
        link.close()
    result['expected_value'] = expected
    result['passed'] = not result['errors'] and result.get('value') == expected
    out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
if not result['passed']:
    raise SystemExit(1)
