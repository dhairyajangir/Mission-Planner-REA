"""Extract one captured simulator MAVLink record and make local truncation controls."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
source = root / 'mission-planner-runtime/isolated-data/logs/SITL/QUADROTOR/1/2026-11-04 10-21-47.tlog'
data = source.read_bytes()
if len(data) < 20 or data[8] not in (0xfd, 0xfe):
    raise ValueError('first log record has unexpected framing')
frame_length = data[9] + (12 if data[8] == 0xfd else 8)
if data[8] == 0xfd and data[10] & 1:
    frame_length += 13
record = data[:8 + frame_length]
if len(record) != 8 + frame_length:
    raise ValueError('first log record truncated')
out = root / 'sitl-evidence/tlog-playback-probe'
out.mkdir(exist_ok=True)
fixtures = {'control.tlog': record, 'truncated-one.tlog': record[:-1],
            'truncated-four.tlog': record[:-4], 'checksum-flipped.tlog': record[:-1] + bytes([record[-1] ^ 1])}
if record[8] != 0xfe or record[13] != 0:
    raise ValueError('expected the first fixture to be a MAVLink 1 heartbeat')

def crc_x25(values):
    crc = 0xffff
    for value in values:
        tmp = value ^ (crc & 0xff)
        tmp ^= (tmp << 4) & 0xff
        crc = ((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xffff
    return crc

frame = bytearray(record[8:])
if crc_x25(frame[1:-2] + bytes([50])) != int.from_bytes(frame[-2:], 'little'):
    raise ValueError('captured heartbeat CRC did not match independent X.25 computation')
for value in range(65536):
    frame[6:8] = value.to_bytes(2, 'little')
    crc = crc_x25(frame[1:-2] + bytes([50]))
    if crc < 256:
        frame[-2:] = crc.to_bytes(2, 'little')
        break
else:
    raise ValueError('could not generate zero high checksum byte')
zero_crc_record = record[:8] + frame
fixtures['zero-crc-control.tlog'] = zero_crc_record
fixtures['zero-crc-truncated.tlog'] = zero_crc_record[:-1]
manifest = {'source': str(source.relative_to(root)), 'source_sha256': hashlib.sha256(data).hexdigest(),
            'record_length': len(record), 'frame_length': frame_length, 'files': {}}
for name, value in fixtures.items():
    target = out / name
    if target.exists() and target.read_bytes() != value:
        raise ValueError('existing fixture differs: ' + name)
    target.write_bytes(value)
    manifest['files'][name] = {'size': len(value), 'sha256': hashlib.sha256(value).hexdigest()}
(out / 'fixtures.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
