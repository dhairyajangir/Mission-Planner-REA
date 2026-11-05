"""Check synthetic sloped HGT samples and Copter terrain frames independently."""
from array import array
import hashlib
import json
import math
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega
out = root / 'sitl-evidence/command-ack-terrain_slope'
fixture = root / 'sitl-evidence/terrain-slope-fixture-data/S36E149.hgt'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
raw = fixture.read_bytes()
assert len(raw) == 1201 * 1201 * 2
samples = array('h'); samples.frombytes(raw)
if sys.byteorder == 'little': samples.byteswap()
assert all(value == (index // 1201) + 2 * (index % 1201) for index, value in enumerate(samples))
relay = json.loads((out / 'relay-result.json').read_text())
assert relay['case'] == 'terrain_slope' and relay['errors'] == [] and relay['closed_by'] == 'client'
assert relay['buffered_bytes_at_close'] == 0
for name, digest in relay['capture_sha256'].items(): assert sha(out / name) == digest
def decode(path):
    parser = ardupilotmega.MAVLink(None); parser.robust_parsing = True
    found, bad = [], 0
    for byte in path.read_bytes():
        msg = parser.parse_char(bytes([byte]))
        if msg is None: continue
        if msg.get_type() == 'BAD_DATA': bad += 1
        elif msg.get_type() in ('HEARTBEAT', 'TERRAIN_DATA', 'TERRAIN_REQUEST', 'TERRAIN_REPORT', 'TERRAIN_CHECK', 'REQUEST_DATA_STREAM'):
            item = msg.to_dict(); item['source'] = [msg.get_srcSystem(), msg.get_srcComponent()]; found.append(item)
    return found, bad
up, bad_up = decode(out / 'to_sitl_output.bin'); down, bad_down = decode(out / 'to_client_output.bin')
checks = [m for m in up if m['mavpackettype'] == 'TERRAIN_CHECK']
streams = [m for m in up if m['mavpackettype'] == 'REQUEST_DATA_STREAM']
data = [m for m in up if m['mavpackettype'] == 'TERRAIN_DATA']
requests = [m for m in down if m['mavpackettype'] == 'TERRAIN_REQUEST' and m['source'] == [1, 1]]
reports = [m for m in down if m['mavpackettype'] == 'TERRAIN_REPORT' and m['source'] == [1, 1]]
heartbeats = [m for m in down if m['mavpackettype'] == 'HEARTBEAT' and m['source'] == [1, 1]]
assert checks and all(m['lat'] == -353632610 and m['lon'] == 1491652300 for m in checks)
assert any(m['req_stream_id'] == 0 and m['req_message_rate'] == 4 and m['start_stop'] == 1 for m in streams)
assert requests and len(data) >= 16 and heartbeats and all(not (m['base_mode'] & 128) for m in heartbeats)
assert all(any(m['lat'] == r['lat'] and m['lon'] == r['lon'] and m['grid_spacing'] == r['grid_spacing'] and
               (r['mask'] & (1 << m['gridbit'])) for r in requests) for m in data)
def offset(lat, lon, east, north):
    phi = math.radians(lat); lam = math.radians(lon)
    bearing = math.atan2(east, north); dr = math.hypot(east, north) / 6378100.0
    phi2 = math.asin(math.sin(phi) * math.cos(dr) + math.cos(phi) * math.sin(dr) * math.cos(bearing))
    lam2 = lam + math.atan2(math.sin(bearing) * math.sin(dr) * math.cos(phi), math.cos(dr) - math.sin(phi) * math.sin(phi2))
    return math.degrees(phi2), math.degrees(lam2)
def height(lat, lon):
    assert -36 <= lat < -35 and 149 <= lon < 150
    return 1200 * (1 - (lat + 36)) + 2400 * (lon - 149)
errors = []
swapped_differences = 0
for block in data:
    bit = block['gridbit']; spacing = block['grid_spacing']
    lat, lon = offset(block['lat'] / 1e7, block['lon'] / 1e7, 4 * spacing * (bit % 8), 4 * spacing * (bit // 8))
    expected = [int(height(*offset(lat, lon, spacing * (i % 4), spacing * (i // 4)))) for i in range(16)]
    swapped = [int(height(*offset(lat, lon, spacing * (i // 4), spacing * (i % 4)))) for i in range(16)]
    swapped_differences += sum(a != b for a, b in zip(block['data'], swapped))
    errors.extend(abs(a - b) for a, b in zip(block['data'], expected))
assert len(errors) == len(data) * 16 and max(errors) <= 1
assert swapped_differences > 0
expected_home = height(-35.363261, 149.165230)
matching = [m for m in reports if m['lat'] == -353632610 and m['lon'] == 1491652300 and m['spacing'] == 100 and m['loaded'] > 0]
assert matching and abs(matching[-1]['terrain_height'] - expected_home) <= 1
log = (out / 'probe.log').read_text(encoding='utf8')
lines = ['FIXTURE_SHA256=' + sha(fixture), 'REQUESTED_ALL_STREAMS_HZ=4', 'FIXTURE_REPORT_MATCH=True']
assert all(line in log for line in lines) and (out / 'probe-exit.txt').read_text().strip() == '0'
paths = {'original_ardupilot': 'mission-planner-portable/MissionPlanner.ArduPilot.dll',
         'test_ardupilot': 'mission-planner-isolated/MissionPlanner.ArduPilot.dll',
         'original_utilities': 'mission-planner-portable/MissionPlanner.Utilities.dll',
         'test_utilities': 'mission-planner-isolated/MissionPlanner.Utilities.dll'}
hashes = {name: sha(root / path) for name, path in paths.items()}
assert hashes['original_ardupilot'] == hashes['test_ardupilot'] and hashes['original_utilities'] != hashes['test_utilities']
summary = {'scope': 'Synthetic sloped HGT; patched Utilities; disposable SITL; no physical navigation',
           'relay': relay, 'fixture_sha256': sha(fixture), 'library_hashes': hashes,
           'probe_source_sha256': sha(out / 'probe-source.cs'), 'probe_exe_sha256': sha(out / 'probe.exe'),
           'probe_log_sha256': sha(out / 'probe.log'), 'checks': checks, 'streams': streams, 'data': data,
           'requests': requests, 'reports': reports, 'heartbeats': heartbeats, 'sample_comparisons': len(errors),
           'max_sample_error_m': max(errors), 'swapped_axis_differences': swapped_differences, 'expected_home_height': expected_home,
           'matched_home_report': matching[-1], 'bad_data_fragments': {'uplink': bad_up, 'downlink': bad_down},
           'verified_probe_lines': lines}
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print('Compared', len(errors), 'samples; max error', max(errors), 'm; home expected', expected_home, 'reported', matching[-1]['terrain_height'])
