"""Make synthetic MAVLink 1 heartbeats for an in-memory parser test."""
import hashlib
import json
from pathlib import Path
import struct

root = Path(__file__).resolve().parent.parent
folder = root / 'sitl-evidence/multivehicle-parser-probe'
folder.mkdir(exist_ok=True)

def crc_x25(data):
    crc = 0xffff
    for value in data:
        tmp = value ^ (crc & 0xff)
        tmp ^= (tmp << 4) & 0xff
        crc = ((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xffff
    return crc

def heartbeat(system, component, kind, autopilot, sequence):
    payload = struct.pack('<IBBBBB', 0, kind, autopilot, 0, 4, 3)
    frame = bytes([0xfe, len(payload), sequence, system, component, 0]) + payload
    return frame + crc_x25(frame[1:] + bytes([50])).to_bytes(2, 'little')

def param_value(system, component, value, sequence):
    payload = struct.pack('<fHH16sB', value, 1, 0, b'TEST_VAL', 9)
    frame = bytes([0xfe, len(payload), sequence, system, component, 22]) + payload
    return frame + crc_x25(frame[1:] + bytes([220])).to_bytes(2, 'little')

v1 = heartbeat(1, 1, 2, 3, 0)
v2 = heartbeat(2, 1, 1, 3, 0)
gcs = heartbeat(255, 190, 6, 8, 0)
component = heartbeat(1, 100, 30, 8, 1)
bad = bytearray(heartbeat(3, 1, 2, 3, 0))
bad[-1] ^= 1
bad_param = bytearray(param_value(2, 1, 99.0, 2))
bad_param[-1] ^= 1
fixtures = {'vehicle-first.bin': v1 + v2 + gcs + component + bad,
            'gcs-first.bin': gcs + v1 + v2,
            'bad-only.bin': bad,
            'param-isolation.bin': v1 + v2 + component + param_value(1, 1, 12.5, 2) +
                                   param_value(2, 1, 87.5, 1) + param_value(1, 100, 42.0, 2) + bad_param}
manifest = {}
for name, value in fixtures.items():
    path = folder / name
    if path.exists() and path.read_bytes() != value:
        raise ValueError('existing fixture differs: ' + name)
    path.write_bytes(value)
    manifest[name] = {'sha256': hashlib.sha256(value).hexdigest(), 'size': len(value),
                      'frame_count': 7 if name == 'param-isolation.bin' else len(value) // 17}
(folder / 'fixtures.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
