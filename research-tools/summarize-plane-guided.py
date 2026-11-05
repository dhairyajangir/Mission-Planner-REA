"""Decode the disarmed Plane guided mission-item experiment."""
from pathlib import Path
import hashlib, json, os, sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega as mav
run = root / 'sitl-evidence/command-ack-plane_guided'
relay = json.loads((run / 'relay-result.json').read_text())
def read(name):
    data = (run / name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == relay['capture_sha256'][name]
    parser = mav.MAVLink(None); parser.robust_parsing = True
    result = []
    for b in data:
        msg = parser.parse_char(bytes([b]))
        if msg and msg.get_type() != 'BAD_DATA': result.append(msg)
    return result
sent = read('to_sitl_output.bin')
received = read('to_client_output.bin')
items = [m.to_dict() for m in sent if m.get_type() in ('MISSION_ITEM', 'MISSION_ITEM_INT')]
acks = [m.to_dict() for m in received if m.get_type() == 'MISSION_ACK' and m.get_srcSystem() == 1 and m.get_srcComponent() == 1]
assert len(items) == 2 and len(acks) == 2, (items, acks)
for item, lat, lon, alt in zip(items, (-35.3631, -35.3632), (149.1651, 149.1652), (21, 22)):
    assert item['mavpackettype'] == 'MISSION_ITEM' and item['current'] == 2
    assert item['target_system'] == 1 and item['target_component'] == 1 and item['seq'] == 0
    assert item['frame'] == 3 and item['command'] == 16 and item['z'] == alt
    assert abs(item['x']-lat) < 0.00001 and abs(item['y']-lon) < 0.00001
assert [a['type'] for a in acks] == [1, 0], acks
indices = [i for i, m in enumerate(sent) if m.get_type() == 'MISSION_ITEM']
mode_indices = [i for i, m in enumerate(sent) if m.get_type() == 'SET_MODE']
assert indices[0] < min(mode_indices) < indices[1]
log = (run / 'probe.log').read_text(errors='replace')
assert 'FIRMWARE=ArduPlane' in log and 'Guided Mode Failed' in log
assert log.index('Guided Mode Failed') < log.index('MANUAL_TARGET_RETURNED') < log.index('GUIDED_TARGET_RETURNED')
assert (run / 'probe-exit.txt').read_text().strip() == '0' and not relay['errors']
summary = {'scope':'disarmed source-built Plane SITL; original Mission Planner library', 'mission_items':items, 'mission_acks':acks,
           'mission_item_indices':indices, 'mode_indices':mode_indices, 'manual_error_logged_but_call_returned':True,
           'outbound_sha256':relay['capture_sha256']['to_sitl_output.bin'], 'inbound_sha256':relay['capture_sha256']['to_client_output.bin'],
           'probe_exit':0}
(run / 'plane-guided-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
