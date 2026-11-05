"""Check Plane mission readback and guided-cache observations against wire captures."""
from pathlib import Path
import hashlib, json, os, sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega as mav
run = root / 'sitl-evidence/command-ack-plane_guided_state'
relay = json.loads((run/'relay-result.json').read_text())
def read(name):
    data = (run/name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == relay['capture_sha256'][name]
    parser = mav.MAVLink(None); parser.robust_parsing = True
    out = []
    for b in data:
        m = parser.parse_char(bytes([b]))
        if m and m.get_type() != 'BAD_DATA': out.append(m)
    return out
sent = read('to_sitl_output.bin'); received = read('to_client_output.bin')
guided = [m.to_dict() for m in sent if m.get_type() == 'MISSION_ITEM' and m.current == 2]
counts = [m.to_dict() for m in received if m.get_type() == 'MISSION_COUNT' and m.get_srcSystem() == 1 and m.get_srcComponent() == 1]
items = [m.to_dict() for m in received if m.get_type() == 'MISSION_ITEM_INT' and m.seq == 1 and m.get_srcSystem() == 1 and m.get_srcComponent() == 1]
acks = [m.to_dict() for m in received if m.get_type() == 'MISSION_ACK' and m.get_srcSystem() == 1 and m.get_srcComponent() == 1]
assert len(guided) == 2 and [m['z'] for m in guided] == [21,22]
assert len(counts) == 3 and all(m['count'] == 2 for m in counts), counts
assert len(items) == 3 and all(m['x'] == -353630000 and m['y'] == 1491655000 and m['z'] == 20 for m in items), items
assert [m['type'] for m in acks][-2:] == [1,0], acks
log = (run/'probe.log').read_text(errors='replace')
lines = ['CACHE_BEFORE x=0 y=0 z=0', 'Guided Mode Failed', 'MANUAL_RETURNED',
         'CACHE_AFTER_REJECTION x=-353630981 y=1491651000 z=21',
         'MISSION_AFTER_REJECTION count=2 lat=-35.363 lon=149.1655 alt=20',
         'GUIDED_RETURNED', 'CACHE_AFTER_ACCEPTANCE x=-353632011 y=1491652069 z=22',
         'MISSION_AFTER_ACCEPTANCE count=2 lat=-35.363 lon=149.1655 alt=20']
assert all(line in log for line in lines) and [log.index(line) for line in lines] == sorted(log.index(line) for line in lines)
assert (run/'probe-exit.txt').read_text().strip() == '0' and not relay['errors']
summary = {'scope':'disarmed source-built Plane; ordinary mission count and item 1 only',
           'guided_items':guided, 'ack_results':[m['type'] for m in acks], 'mission_counts':[m['count'] for m in counts],
           'readback_items':items, 'cache_after_rejection':[-353630981,1491651000,21],
           'cache_after_acceptance':[-353632011,1491652069,22],
           'outbound_sha256':relay['capture_sha256']['to_sitl_output.bin'], 'inbound_sha256':relay['capture_sha256']['to_client_output.bin'], 'probe_exit':0}
(run/'state-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
