"""Independently inspect a captured selective PARAM_VALUE loss experiment."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink import mavutil

run_name = os.environ.get('MP_VERIFY_RUN', 'archive-param-index-loss')
if Path(run_name).name != run_name:
    raise ValueError('run name must be a single directory')
run = root / 'sitl-evidence' / run_name
proxy = json.loads((run / 'proxy-result.json').read_text())
if proxy['mode'] == 'param_values':
    expected = list(range(20, 30))
elif proxy['mode'] == 'param_bulk':
    expected = list(range(500))
elif proxy['mode'] == 'param_repeat':
    expected = [20, 20, 20]
else:
    raise ValueError('unsupported loss mode')
source = (run / 'to_client_input.bin').read_bytes()
actual = (run / 'to_client_output.bin').read_bytes()
uplink = (run / 'to_sitl_input.bin').read_bytes()
forwarded_uplink = (run / 'to_sitl_output.bin').read_bytes()
dropped = (run / 'dropped.bin').read_bytes()
errors = []


def frames(data, permit_text=False):
    i = 0
    while i < len(data):
        magic = data[i]
        if magic not in (0xfe, 0xfd):
            if not permit_text:
                raise ValueError('unexpected non-frame byte')
            yield data[i:i+1], None
            i += 1
            continue
        hdr = 6 if magic == 0xfe else 10
        if i + hdr > len(data):
            raise ValueError('truncated header')
        length = data[i+1] + (8 if magic == 0xfe else 12)
        if magic == 0xfd and data[i+2] & 1:
            length += 13
        packet = data[i:i+length]
        if len(packet) != length:
            raise ValueError('truncated packet')
        yield packet, magic
        i += length


dropped_packets = []
dropped_indices = []
for packet, _ in frames(dropped):
    msg = mavutil.mavlink.MAVLink(None).parse_char(packet)
    if not msg or msg.get_type() != 'PARAM_VALUE':
        raise ValueError('dropped packet is not a valid PARAM_VALUE')
    dropped_packets.append(packet)
    dropped_indices.append(msg.param_index)
rebuilt = bytearray()
next_removed = 0
for packet, _ in frames(source, permit_text=True):
    if next_removed < len(dropped_packets) and packet == dropped_packets[next_removed]:
        next_removed += 1
    else:
        rebuilt.extend(packet)
counts = Counter()
requested = []
for packet, _ in frames(uplink):
    msg = mavutil.mavlink.MAVLink(None).parse_char(packet)
    if not msg:
        raise ValueError('uplink packet did not decode')
    counts[msg.get_type()] += 1
    if msg.get_type() == 'PARAM_REQUEST_READ':
        requested.append(msg.param_index)
recovered = {}
for packet, magic in frames(actual, permit_text=True):
    if magic is None:
        continue
    message_id = packet[5] if magic == 0xfe else packet[7] | packet[8] << 8 | packet[9] << 16
    if message_id == 22:
        msg = mavutil.mavlink.MAVLink(None).parse_char(packet)
        if msg and msg.param_index in dropped_indices:
            recovered[str(msg.param_index)] = msg.param_id
out = {'scope': 'offline capture comparison and independent MAVLink decoding',
       'dropped_indexes': dropped_indices, 'requested_indexes': requested,
       'forwarded_recovered_indexes': recovered,
       'uplink_counts': dict(counts), 'downlink_matches_filtered_input': bytes(rebuilt) == actual,
       'uplink_unchanged': uplink == forwarded_uplink, 'matched_dropped_packets': next_removed,
       'downlink_input_sha256': hashlib.sha256(source).hexdigest(),
       'downlink_output_sha256': hashlib.sha256(actual).hexdigest(),
       'uplink_input_sha256': hashlib.sha256(uplink).hexdigest(),
       'uplink_output_sha256': hashlib.sha256(forwarded_uplink).hexdigest(),
       'dropped_sha256': hashlib.sha256(dropped).hexdigest(), 'errors': errors}
if proxy['mode'] == 'param_values':
    recovery_requests_ok = set(dropped_indices).issubset(requested) and counts['PARAM_REQUEST_LIST'] >= 1
elif proxy['mode'] == 'param_bulk':
    recovery_requests_ok = counts['PARAM_REQUEST_LIST'] >= 2
else:
    recovery_requests_ok = requested.count(20) >= 3 and counts['PARAM_REQUEST_LIST'] >= 1
out['passed'] = (not errors and proxy['passed'] and sorted(dropped_indices) == expected and
                 recovery_requests_ok and
                 set(map(int, recovered)) == set(dropped_indices) and
                 out['downlink_matches_filtered_input'] and out['uplink_unchanged'] and
                 next_removed == len(dropped_packets) == len(expected))
(run / 'stream-verification.json').write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps(out, indent=2))
if not out['passed']:
    raise SystemExit(1)
