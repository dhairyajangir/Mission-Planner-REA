"""Generate synthetic signed-flag MAVLink 2 log frames with arbitrary signature bytes."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
control = (root / 'sitl-evidence/tlog-playback-probe/control.tlog').read_bytes()
if len(control) != 25 or control[8] != 0xfe or control[13] != 0:
    raise ValueError('unexpected source heartbeat')
timestamp, mav1 = control[:8], control[8:]
payload = mav1[6:-2]
header = bytes([0xfd, len(payload), 1, 0, 0, 255, 190, 0, 0, 0])
def crc_x25(data):
    crc = 0xffff
    for value in data:
        tmp = value ^ (crc & 0xff)
        tmp ^= (tmp << 4) & 0xff
        crc = ((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xffff
    return crc

frame = header + payload
frame += crc_x25(frame[1:] + bytes([50])).to_bytes(2, 'little')
signature_a = bytes(13)
signature_b = bytes([0x55] * 13)
bad_frame = bytearray(frame)
bad_frame[10] ^= 1
fixtures = {'arbitrary-signature-a.tlog': timestamp + frame + signature_a,
            'arbitrary-signature-b.tlog': timestamp + frame + signature_b,
            'payload-flipped.tlog': timestamp + bad_frame + signature_a}
out = root / 'sitl-evidence/tlog-signature-probe'
out.mkdir(exist_ok=True)
manifest = {'control_sha256': hashlib.sha256(control).hexdigest(), 'files': {}}
for name, contents in fixtures.items():
    path = out / name
    if path.exists() and path.read_bytes() != contents:
        raise ValueError('fixture changed: ' + name)
    path.write_bytes(contents)
    manifest['files'][name] = {'size': len(contents), 'sha256': hashlib.sha256(contents).hexdigest()}
(out / 'fixtures.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
