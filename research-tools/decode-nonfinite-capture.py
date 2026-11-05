"""Decode captured MAVLink streams without modifying or replaying them."""
import hashlib
import json
import math
from pathlib import Path
import sys

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
from pymavlink.dialects.v20 import ardupilotmega as mav

folder = root / 'sitl-evidence/missionplanner-nonfinite-capture'
proxy = json.loads((folder / 'proxy-result.json').read_text())
decoded = {'scope': 'Offline decode of passive localhost byte capture; no GUI or physical vehicle',
           'binary_sha256': proxy['binary_sha256'], 'directions': {}}
for direction in ('uplink', 'downlink'):
    path = folder / (direction + '.bin')
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != proxy[direction + '_sha256'] or len(data) != proxy['bytes'][direction]:
        raise ValueError('capture hash or size mismatch: ' + direction)
    parser = mav.MAVLink(None)
    parser.robust_parsing = True
    messages, bad, bad_reasons, bad_samples, bad_offsets = [], 0, {}, [], []
    for offset, byte in enumerate(data):
        message = parser.parse_char(bytes([byte]))
        if message is None:
            continue
        kind = message.get_type()
        if kind == 'BAD_DATA':
            bad += 1
            reason = str(message.reason)
            bad_reasons[reason] = bad_reasons.get(reason, 0) + 1
            bad_offsets.append(offset)
            if len(bad_samples) < 8:
                bad_samples.append({'reason': reason, 'data_hex': bytes(message.data).hex()})
        elif kind in ('PARAM_SET', 'PARAM_ERROR', 'PARAM_VALUE', 'PARAM_REQUEST_READ') and str(message.param_id).rstrip('\x00') == 'LOG_DISARMED':
            row = {'type': kind, 'source_system': message.get_srcSystem(),
                   'source_component': message.get_srcComponent(),
                   'frame_sha256': hashlib.sha256(message.get_msgbuf()).hexdigest()}
            if kind in ('PARAM_SET', 'PARAM_VALUE'):
                value = message.param_value
                row['value'] = 'NaN' if math.isnan(value) else ('Infinity' if math.isinf(value) else value)
            if kind == 'PARAM_ERROR':
                row['error'] = message.error
                row['target_system'] = message.target_system
                row['target_component'] = message.target_component
            messages.append(row)
    decoded['directions'][direction] = {'sha256': digest, 'size': len(data), 'bad_data_records': bad,
                                        'bad_data_reasons': bad_reasons, 'bad_data_samples': bad_samples,
                                        'bad_data_feed_offsets': bad_offsets,
                                        'messages': messages}

up = decoded['directions']['uplink']['messages']
down = decoded['directions']['downlink']['messages']
nan_writes = [row for row in up if row['type'] == 'PARAM_SET' and row['value'] == 'NaN']
errors = [row for row in down if row['type'] == 'PARAM_ERROR' and row['error'] == 2]
values = [row['value'] for row in down if row['type'] == 'PARAM_VALUE']
decoded['checks'] = {'proxy_clean': not proxy['errors'] and proxy['ended_by'] == 'client_eof',
                     'four_nan_writes': len(nan_writes) == 4,
                     'four_out_of_range_errors': len(errors) == 4,
                     'finite_set_and_restore': any(row['type'] == 'PARAM_SET' and row['value'] == 1 for row in up) and
                                               any(row['type'] == 'PARAM_SET' and row['value'] == 0 for row in up),
                     'finite_values_received': 1 in values and 0 in values}
decoded['passed'] = all(decoded['checks'].values())
(folder / 'decoded.json').write_text(json.dumps(decoded, indent=2) + '\n')
print(json.dumps(decoded, indent=2))
if not decoded['passed']:
    raise SystemExit(1)
