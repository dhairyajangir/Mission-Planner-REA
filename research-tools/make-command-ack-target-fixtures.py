"""Generate MAVLink 2 ACKs with matched and mismatched target extensions."""
import hashlib
import json
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
from pymavlink.dialects.v20 import ardupilotmega as mav
out = root / 'sitl-evidence/command-ack-target-synthetic'
out.mkdir(exist_ok=False)
def ack(result, target_system, target_component):
    sender = mav.MAVLink(None, srcSystem=1, srcComponent=1)
    return mav.MAVLink_command_ack_message(510, result, target_system=target_system,
                                           target_component=target_component).pack(sender)
cases = {'wrong-target-then-denied': ack(0, 42, 17) + ack(2, 255, 190),
         'matching-denied': ack(2, 255, 190), 'broadcast-accepted': ack(0, 0, 0)}
manifest = {}
for name, data in cases.items():
    (out / (name + '.bin')).write_bytes(data)
    manifest[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
(out / 'fixtures.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
