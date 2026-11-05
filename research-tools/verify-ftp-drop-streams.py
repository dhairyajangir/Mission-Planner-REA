"""Verify captured proxy streams differ only by valid MAVLink FTP frames."""
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
import sys

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink import mavutil

run = root / 'sitl-evidence/archive-param-ftp-drop-2'
proxy = json.loads((run / 'proxy-result.json').read_text())
source = (run / 'to_client_input.bin').read_bytes()
actual = (run / 'to_client_output.bin').read_bytes()
uplink_source = (run / 'to_sitl_input.bin').read_bytes()
uplink_output = (run / 'to_sitl_output.bin').read_bytes()
removed = (run / 'dropped.bin').read_bytes()
uplink_counts = Counter()
uplink_parser = mavutil.mavlink.MAVLink(None)
try:
    for byte in uplink_source:
        message = uplink_parser.parse_char(bytes([byte]))
        if message is not None:
            uplink_counts[message.get_type()] += 1
except Exception as exc:
    raise RuntimeError('uplink MAVLink decode failed') from exc
reconstructed = bytearray()
removed_frames = []
stray = bytearray()
errors = []
i = 0
while i < len(source):
    magic = source[i]
    if magic not in (0xfe, 0xfd):
        stray.append(magic)
        reconstructed.append(magic)
        i += 1
        continue
    header = 6 if magic == 0xfe else 10
    if len(source) - i < header:
        errors.append('incomplete frame header')
        break
    length = source[i + 1] + (8 if magic == 0xfe else 12)
    if magic == 0xfd and source[i + 2] & 1:
        length += 13
    packet = source[i:i + length]
    if len(packet) != length:
        errors.append('incomplete frame')
        break
    msgid = source[i + 5] if magic == 0xfe else source[i + 7] | source[i + 8] << 8 | source[i + 9] << 16
    if msgid == 110:
        try:
            decoded = mavutil.mavlink.MAVLink(None).parse_char(packet)
            if not decoded or decoded.get_type() != 'FILE_TRANSFER_PROTOCOL':
                errors.append('dropped packet did not decode as MAVLink FTP')
            removed_frames.append(packet)
        except Exception as exc:
            errors.append('dropped packet decode failed: ' + str(exc))
    else:
        reconstructed.extend(packet)
    i += length

summary = {'scope': 'offline comparison of captured proxy streams, with independent CRC decoding of dropped frames',
           'downlink_input_sha256': hashlib.sha256(source).hexdigest(),
           'downlink_output_sha256': hashlib.sha256(actual).hexdigest(),
           'uplink_input_sha256': hashlib.sha256(uplink_source).hexdigest(),
           'uplink_output_sha256': hashlib.sha256(uplink_output).hexdigest(),
           'stray_bytes': len(stray), 'stray_hex': stray.hex(),
           'dropped_valid_ftp_frames': len(removed_frames),
           'uplink_message_counts': dict(uplink_counts),
           'downlink_matches_filtered_input': bytes(reconstructed) == actual,
           'uplink_unchanged': uplink_source == uplink_output,
           'dropped_capture_matches': b''.join(removed_frames) == removed,
           'errors': errors}
summary['passed'] = (not errors and summary['downlink_matches_filtered_input'] and summary['uplink_unchanged'] and
                     summary['dropped_capture_matches'] and len(removed_frames) == proxy['ftp_replies_dropped'] > 0 and
                     uplink_counts['FILE_TRANSFER_PROTOCOL'] > 0 and uplink_counts['PARAM_REQUEST_LIST'] > 0)
(run / 'stream-verification.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
if not summary['passed']:
    raise SystemExit(1)
