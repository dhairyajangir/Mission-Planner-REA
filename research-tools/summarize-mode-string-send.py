"""Decode captured string-based tracker mode writes."""
import hashlib
import json
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega
out = root / 'sitl-evidence/mode-translation-synthetic'
data = (out / 'string-send.bin').read_bytes()
parser = ardupilotmega.MAVLink(None)
frames = []
for byte in data:
    msg = parser.parse_char(bytes([byte]))
    if msg is not None:
        item = msg.to_dict(); item['source'] = [msg.get_srcSystem(), msg.get_srcComponent()]
        frames.append(item)
assert [x['mavpackettype'] for x in frames] == ['COMMAND_LONG', 'SET_MODE', 'SET_MODE']
assert frames[0]['command'] == 176 and frames[0]['target_system'] == 1 and frames[0]['target_component'] == 1
assert frames[0]['param1'] == 1 and frames[0]['param2'] == 2
assert all(x['target_system'] == 1 and x['base_mode'] == 1 and x['custom_mode'] == 2 for x in frames[1:])
log = (out / 'string-send.log').read_text(encoding='utf-16').splitlines()
assert log == ['INVALID_BYTES=0', 'VALID_BYTES=' + str(len(data))]
(out / 'string-send-summary.json').write_text(json.dumps({'scope': 'Original tracker string setter, in-memory capture',
    'capture_sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'frames': frames, 'log_lines': log}, indent=2) + '\n')
print('decoded', len(frames), 'mode-setting frames')
