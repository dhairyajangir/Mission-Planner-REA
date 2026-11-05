"""Independently decode the simulated flight's captured MAVLink streams."""
import hashlib, json, math, os, re, sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega as mav
run = root / 'sitl-evidence/command-ack-guided_flight_retry'
relay = json.loads((run / 'relay-result.json').read_text())
def decode(name):
    data = (run / name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == relay['capture_sha256'][name]
    parser = mav.MAVLink(None); parser.robust_parsing = True
    messages = []
    for byte in data:
        m = parser.parse_char(bytes([byte]))
        if m and m.get_type() != 'BAD_DATA': messages.append(m)
    return messages
outbound = decode('to_sitl_output.bin')
inbound = decode('to_client_output.bin')
targets = [m for m in outbound if m.get_type() == 'SET_POSITION_TARGET_GLOBAL_INT']
assert len(targets) == 1
target = targets[0].to_dict()
assert target['coordinate_frame'] == 6 and target['type_mask'] == 65016 and target['alt'] == 5
positions = [m for m in inbound if m.get_type() == 'GLOBAL_POSITION_INT' and m.get_srcSystem() == 1 and m.get_srcComponent() == 1]
heartbeats = [m for m in inbound if m.get_type() == 'HEARTBEAT' and m.get_srcSystem() == 1 and m.get_srcComponent() == 1]
assert positions and max(p.relative_alt for p in positions) >= 3500
airborne = [p for p in positions if p.relative_alt >= 3000]
assert airborne
def distance(p):
    return math.hypot((p.lat-target['lat_int'])*0.011132, (p.lon-target['lon_int'])*0.011132*math.cos(math.radians(p.lat/1e7)))
closest = min(airborne, key=distance)
assert distance(closest) < 2.5
assert any((h.base_mode & 128) and h.custom_mode == 4 for h in heartbeats)
assert any((h.base_mode & 128) and h.custom_mode == 9 for h in heartbeats)
assert heartbeats[-1].custom_mode == 9 and not (heartbeats[-1].base_mode & 128)
commands = [m.to_dict() for m in outbound if m.get_type() == 'COMMAND_LONG']
assert any(m['command'] == 400 and m['param1'] == 1 and m['param2'] == 0 for m in commands)
assert any(m['command'] == 22 and m['param7'] == 5 for m in commands)
log = (run / 'probe.log').read_text(errors='replace')
match = re.search(r'TARGET (-?\d+\.\d+) (-?\d+\.\d+) 5', log)
assert match and abs(float(match.group(1))*1e7 - target['lat_int']) <= 2 and abs(float(match.group(2))*1e7 - target['lon_int']) <= 2
pos_re = re.compile(r'^POS (-?\d+\.\d+) (-?\d+\.\d+) (-?\d+\.\d+)', re.MULTILINE)
before = list(pos_re.finditer(log[:match.start()]))
after = list(pos_re.finditer(log[match.end():]))
assert before and after
start = tuple(map(float, before[-1].groups()))
assert start[2] >= 3.5 and abs(start[0] - target['lat_int']/1e7) >= 0.00007
assert any(abs(float(m.group(1))-target['lat_int']/1e7) < 0.000015 and
           abs(float(m.group(2))-target['lon_int']/1e7) < 0.00002 and float(m.group(3)) >= 3
           for m in after)
assert 'ARM_ATTEMPT=1 ACCEPTED=True' in log and 'TAKEOFF_ACCEPTED=True' in log and 'FLIGHT_SUCCESS disarmed=True' in log
assert (run / 'probe-exit.txt').read_text().strip() == '0' and not relay['errors']
summary = {'scope':'disposable source-built Copter SITL; original Mission Planner library; no UI or physical aircraft',
           'target':target, 'logged_position_before_target':start, 'closest_airborne_position':closest.to_dict(), 'closest_airborne_distance_m':distance(closest),
           'peak_relative_altitude_m':max(p.relative_alt for p in positions)/1000,
           'final_heartbeat':heartbeats[-1].to_dict(), 'outbound_sha256':relay['capture_sha256']['to_sitl_output.bin'],
           'inbound_sha256':relay['capture_sha256']['to_client_output.bin'], 'probe_exit':0}
(run / 'guided-flight-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
