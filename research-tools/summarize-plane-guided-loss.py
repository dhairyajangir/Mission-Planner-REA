"""Decode Plane guided waypoint retry and ACK-loss captures."""
from pathlib import Path
import hashlib, json, os, re, sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega as mav
for case, expected_sent, expected_dropped, expected_delivered in (
        ('plane_guided_drop_one', 2, 1, 1), ('plane_guided_drop_all', 11, 11, 0)):
    run = root / ('sitl-evidence/command-ack-' + case)
    relay = json.loads((run / 'relay-result.json').read_text())
    def read(name):
        data = (run / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == relay['capture_sha256'][name]
        parser = mav.MAVLink(None); parser.robust_parsing = True
        result = []
        for b in data:
            m = parser.parse_char(bytes([b]))
            if m and m.get_type() != 'BAD_DATA': result.append(m)
        return result
    sent = read('to_sitl_output.bin')
    received = read('to_client_input.bin')
    delivered = read('to_client_output.bin')
    dropped = read('dropped.bin')
    items = [m.to_dict() for m in sent if m.get_type() == 'MISSION_ITEM']
    ack = lambda seq: [m.to_dict() for m in seq if m.get_type() == 'MISSION_ACK' and m.get_srcSystem() == 1 and m.get_srcComponent() == 1]
    observed_acks, delivered_acks, dropped_acks = ack(received), ack(delivered), ack(dropped)
    assert len(items) == expected_sent and len(observed_acks) == expected_sent
    assert len(dropped_acks) == expected_dropped == relay['dropped_mission_acks'] and len(delivered_acks) == expected_delivered
    assert all(a['type'] == 0 and (a['target_system'], a['target_component']) == (255,190) for a in observed_acks)
    assert all(i['current'] == 2 and i['frame'] == 3 and i['command'] == 16 and i['z'] == 22 and
               abs(i['x'] + 35.3632) < .00001 and abs(i['y'] - 149.1652) < .00001 for i in items)
    log = (run / 'probe.log').read_text(errors='replace')
    assert 'FIRMWARE=ArduPlane' in log and 'BEFORE x=0 y=0 z=0' in log and 'RETURNED elapsed_ms=' in log
    elapsed = int(re.search(r'RETURNED elapsed_ms=(\d+)', log).group(1))
    if case.endswith('drop_all'):
        assert 'Timeout on read - setWP' in log and 'AFTER x=0 y=0 z=0' in log
    else:
        assert 'MAV_MISSION_ACCEPTED' in log and 'AFTER x=-353632011 y=1491652069 z=22' in log
    assert (run/'probe-exit.txt').read_text().strip() == '0' and not relay['errors']
    summary = {'case':case, 'sent_items':len(items), 'simulator_accepted_acks':len(observed_acks),
               'dropped_acks':len(dropped_acks), 'delivered_acks':len(delivered_acks), 'elapsed_ms':elapsed,
               'timeout_logged': 'Timeout on read - setWP' in log, 'returned_to_caller':True,
               'guided_state_after': re.search(r'AFTER x=(-?\d+) y=(-?\d+) z=(-?[\d.]+)', log).groups(),
               'hashes':{name:relay['capture_sha256'][name] for name in ('to_sitl_output.bin','to_client_input.bin','to_client_output.bin','dropped.bin')}}
    (run/'loss-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
