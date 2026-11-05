"""Construct synthetic MAVLink 1 COMMAND_ACK frames with pymavlink."""
import hashlib
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
from pymavlink.dialects.v10 import ardupilotmega as mav

out = root / 'sitl-evidence/command-ack-synthetic'
out.mkdir(exist_ok=False)
def ack(system, component, command, result):
    sender = mav.MAVLink(None, srcSystem=system, srcComponent=component)
    return mav.MAVLink_command_ack_message(command, result).pack(sender)

accepted = ack(1, 1, 510, mav.MAV_RESULT_ACCEPTED)
denied = ack(1, 1, 510, mav.MAV_RESULT_DENIED)
cases = {
    'wrong-system': ack(2, 1, 510, mav.MAV_RESULT_ACCEPTED) + denied,
    'wrong-component': ack(1, 2, 510, mav.MAV_RESULT_ACCEPTED) + denied,
    'wrong-command': ack(1, 1, 511, mav.MAV_RESULT_ACCEPTED) + denied,
    'in-progress': ack(1, 1, 510, mav.MAV_RESULT_IN_PROGRESS) + accepted,
    'denied': denied,
    'no-ack': denied,
}
manifest = {}
for name, data in cases.items():
    (out / (name + '.bin')).write_bytes(data)
    manifest[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
(out / 'fixtures.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
