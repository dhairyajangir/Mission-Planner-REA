"""Generate non-secret synthetic MAVLink 2 heartbeat frames for an in-memory transport."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
control = (root / 'sitl-evidence/tlog-playback-probe/control.tlog').read_bytes()
payload = control[14:-2]
if len(payload) != 9:
    raise ValueError('unexpected captured heartbeat')
key = bytes(range(32))  # Public test data, never used for a vehicle.

def crc_x25(data):
    crc = 0xffff
    for value in data:
        tmp = value ^ (crc & 0xff)
        tmp ^= (tmp << 4) & 0xff
        crc = ((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xffff
    return crc

def frame(signed):
    packet = bytes([0xfd, len(payload), int(signed), 0, 0, 1, 1, 0, 0, 0]) + payload
    packet += crc_x25(packet[1:] + bytes([50])).to_bytes(2, 'little')
    if signed:
        signature_header = bytes([7]) + (123456789).to_bytes(6, 'little')
        packet += signature_header + hashlib.sha256(key + packet + signature_header).digest()[:6]
    return packet

signed = frame(True)
bad_signature = signed[:-1] + bytes([signed[-1] ^ 1])
unsigned = frame(False)
fixtures = {'signed.bin': signed, 'bad-signature.bin': bad_signature,
            'signed-twice.bin': signed + signed, 'unsigned.bin': unsigned,
            'signed-then-unsigned.bin': signed + unsigned}
out = root / 'sitl-evidence/live-signing-probe'
out.mkdir(exist_ok=True)
manifest = {'control_sha256': hashlib.sha256(control).hexdigest(),
            'test_key_hex': key.hex(), 'files': {}}
for name, value in fixtures.items():
    path = out / name
    if path.exists() and path.read_bytes() != value:
        raise ValueError('existing fixture differs: ' + name)
    path.write_bytes(value)
    manifest['files'][name] = {'size': len(value), 'sha256': hashlib.sha256(value).hexdigest()}
(out / 'fixtures.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
