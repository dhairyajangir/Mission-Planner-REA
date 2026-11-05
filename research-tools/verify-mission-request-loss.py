"""Verify captured mission-request loss and decode the subsequent exchange."""
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

run_name = os.environ.get('MP_VERIFY_RUN', 'archive-mission-request-loss')
if Path(run_name).name != run_name:
    raise ValueError('run name must be a single directory')
run = root / 'sitl-evidence' / run_name
proxy = json.loads((run / 'proxy-result.json').read_text())
source = (run / 'to_client_input.bin').read_bytes()
actual = (run / 'to_client_output.bin').read_bytes()
uplink = (run / 'to_sitl_input.bin').read_bytes()
uplink_out = (run / 'to_sitl_output.bin').read_bytes()
dropped = (run / 'dropped.bin').read_bytes()


def frames(data, text=False):
    i = 0
    while i < len(data):
        magic = data[i]
        if magic not in (0xfe, 0xfd):
            if not text:
                raise ValueError('unexpected non-MAVLink byte')
            yield data[i:i+1], None
            i += 1
            continue
        hdr = 6 if magic == 0xfe else 10
        if i + hdr > len(data):
            raise ValueError('truncated MAVLink header')
        length = data[i+1] + (8 if magic == 0xfe else 12)
        if magic == 0xfd and data[i+2] & 1:
            length += 13
        packet = data[i:i+length]
        if len(packet) != length:
            raise ValueError('truncated MAVLink frame')
        yield packet, magic
        i += length


dropped_frame = list(frames(dropped))
if len(dropped_frame) != 1:
    raise ValueError('expected one dropped frame')
lost = mavutil.mavlink.MAVLink(None).parse_char(dropped_frame[0][0])
expected = ('MISSION_REQUEST', 'MISSION_REQUEST_INT') if proxy['mode'] == 'mission_request' else ('MISSION_ACK',)
if not lost or lost.get_type() not in expected:
    raise ValueError('dropped frame is not the expected valid mission message')
rebuilt = bytearray()
matched = 0
down_requests, down_acks, readback_items = [], [], []
for packet, magic in frames(source, text=True):
    if packet == dropped and matched == 0:
        matched += 1
        continue
    rebuilt.extend(packet)
    if magic is not None:
        mid = packet[5] if magic == 0xfe else packet[7] | packet[8] << 8 | packet[9] << 16
        if mid in (40, 51, 47, 39, 73):
            msg = mavutil.mavlink.MAVLink(None).parse_char(packet)
            if msg.get_type() in ('MISSION_REQUEST', 'MISSION_REQUEST_INT'):
                down_requests.append({'type': msg.get_type(), 'seq': msg.seq})
            elif msg.get_type() == 'MISSION_ACK':
                down_acks.append(msg.type)
            else:
                readback_items.append({'type': msg.get_type(), 'seq': msg.seq, 'x': msg.x, 'y': msg.y, 'z': msg.z})
counts = Counter()
mission_counts, items = [], []
for packet, _ in frames(uplink):
    msg = mavutil.mavlink.MAVLink(None).parse_char(packet)
    if not msg:
        raise ValueError('uplink frame did not decode')
    kind = msg.get_type()
    counts[kind] += 1
    if kind == 'MISSION_COUNT':
        mission_counts.append(msg.count)
    if kind in ('MISSION_ITEM', 'MISSION_ITEM_INT'):
        items.append({'type': kind, 'seq': msg.seq, 'x': msg.x, 'y': msg.y, 'z': msg.z})
lost_info = {'type': lost.get_type()}
if lost.get_type() == 'MISSION_ACK':
    lost_info['ack_type'] = lost.type
else:
    lost_info['seq'] = lost.seq
result = {'scope': 'captured local proxy stream comparison and independent MAVLink decoding',
          'dropped_request': lost_info,
          'forwarded_requests': down_requests, 'forwarded_ack_types': down_acks,
          'readback_items': readback_items,
          'uplink_counts': dict(counts), 'mission_counts': mission_counts, 'uploaded_items': items,
          'downlink_matches_filtered_input': bytes(rebuilt) == actual, 'uplink_unchanged': uplink == uplink_out,
          'matched_dropped_frames': matched,
          'input_sha256': hashlib.sha256(source).hexdigest(), 'output_sha256': hashlib.sha256(actual).hexdigest(),
          'uplink_sha256': hashlib.sha256(uplink).hexdigest(), 'dropped_sha256': hashlib.sha256(dropped).hexdigest()}
if proxy['mode'] == 'mission_request':
    scenario_passed = (lost.seq == 0 and any(x['seq'] == 0 for x in down_requests) and 0 in down_acks)
else:
    scenario_passed = (lost.type == 0 and sum(x['seq'] == 1 for x in items) >= 2 and 1 in down_acks and
                       any(x['seq'] == 1 and abs(x['z'] - 20) < .01 for x in readback_items))
result['passed'] = (proxy['passed'] and scenario_passed and matched == 1 and
                    result['downlink_matches_filtered_input'] and result['uplink_unchanged'] and
                    {0, 1}.issubset({x['seq'] for x in items}))
(run / 'stream-verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
if not result['passed']:
    raise SystemExit(1)
