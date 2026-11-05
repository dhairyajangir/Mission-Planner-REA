"""Validate the all-void terrain fixture and its SITL packet exchange."""
import hashlib
import json
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega
out = root / 'sitl-evidence/command-ack-terrain_invalid'
fixture = root / 'sitl-evidence/terrain-invalid-fixture-data/S36E149.hgt'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
raw = fixture.read_bytes()
assert raw == bytes([128, 0]) * (1201 * 1201)
relay = json.loads((out / 'relay-result.json').read_text())
assert relay['case'] == 'terrain_invalid' and relay['errors'] == [] and relay['closed_by'] == 'client'
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
assert len(requests) >= 2 and not data and reports and heartbeats
assert all(m['pending'] > 0 and m['loaded'] == 0 for m in reports)
assert all(not (m['base_mode'] & 128) for m in heartbeats)
log = (out / 'probe.log').read_text(encoding='utf8')
lines = ['FIXTURE_SHA256=' + sha(fixture), 'SRTM_TYPE=invalid', 'REQUESTED_ALL_STREAMS_HZ=4', 'REQUEST_COUNT=23 PENDING_REPORT_COUNT=66']
assert all(line in log for line in lines) and (out / 'probe-exit.txt').read_text().strip() == '0'
paths = {'original_ardupilot': 'mission-planner-portable/MissionPlanner.ArduPilot.dll',
         'test_ardupilot': 'mission-planner-isolated/MissionPlanner.ArduPilot.dll',
         'original_utilities': 'mission-planner-portable/MissionPlanner.Utilities.dll',
         'test_utilities': 'mission-planner-isolated/MissionPlanner.Utilities.dll'}
hashes = {name: sha(root / path) for name, path in paths.items()}
assert hashes['original_ardupilot'] == hashes['test_ardupilot'] and hashes['original_utilities'] != hashes['test_utilities']
summary = {'scope': 'Synthetic all-void HGT; patched Utilities; disposable SITL; finite observation',
           'relay': relay, 'fixture_sha256': sha(fixture), 'library_hashes': hashes,
           'probe_source_sha256': sha(out / 'probe-source.cs'), 'probe_exe_sha256': sha(out / 'probe.exe'),
           'probe_log_sha256': sha(out / 'probe.log'), 'checks': checks, 'streams': streams, 'data': data,
           'requests': requests, 'reports': reports, 'heartbeats': heartbeats,
           'bad_data_fragments': {'uplink': bad_up, 'downlink': bad_down}, 'verified_probe_lines': lines}
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print('Decoded', len(requests), 'terrain requests,', len(reports), 'pending reports and zero terrain-data frames')
