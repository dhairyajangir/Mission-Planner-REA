"""Decode one dropped terrain block and its later retransmission."""
import hashlib
import json
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega
out = root / 'sitl-evidence/command-ack-terrain_drop_one'
fixture = root / 'sitl-evidence/terrain-fixture-data/S36E149.hgt'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert fixture.read_bytes() == (321).to_bytes(2, 'big', signed=True) * (1201 * 1201)
relay = json.loads((out / 'relay-result.json').read_text())
assert relay['case'] == 'terrain_drop_one' and relay['errors'] == [] and relay['closed_by'] == 'client'
assert relay['buffered_bytes_at_close'] == 0 and relay['dropped_terrain'] == 1
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
incoming, bad_in = decode(out / 'to_sitl_input.bin')
outgoing, bad_out = decode(out / 'to_sitl_output.bin')
dropped, bad_drop = decode(out / 'dropped.bin')
down, bad_down = decode(out / 'to_client_output.bin')
sent = [m for m in incoming if m['mavpackettype'] == 'TERRAIN_DATA']
delivered = [m for m in outgoing if m['mavpackettype'] == 'TERRAIN_DATA']
lost = [m for m in dropped if m['mavpackettype'] == 'TERRAIN_DATA']
requests = [m for m in down if m['mavpackettype'] == 'TERRAIN_REQUEST' and m['source'] == [1, 1]]
reports = [m for m in down if m['mavpackettype'] == 'TERRAIN_REPORT' and m['source'] == [1, 1]]
heartbeats = [m for m in down if m['mavpackettype'] == 'HEARTBEAT' and m['source'] == [1, 1]]
assert len(lost) == 1 and lost[0]['gridbit'] == 0 and sent[0] == lost[0] and sent[1:] == delivered
assert all(m['data'] == [321] * 16 for m in sent)
matches = [m for m in delivered if (m['lat'], m['lon'], m['grid_spacing'], m['gridbit']) ==
           (lost[0]['lat'], lost[0]['lon'], lost[0]['grid_spacing'], lost[0]['gridbit'])]
matching_requests = [m for m in requests if (m['lat'], m['lon'], m['grid_spacing']) ==
                     (lost[0]['lat'], lost[0]['lon'], lost[0]['grid_spacing']) and (m['mask'] & 1)]
assert matches and len(matching_requests) >= 2 and any(m['mask'] == 1 for m in matching_requests)
assert any(m['lat'] == -353632610 and m['lon'] == 1491652300 and m['terrain_height'] == 321 for m in reports)
assert heartbeats and all(not (m['base_mode'] & 128) for m in heartbeats)
log = (out / 'probe.log').read_text(encoding='utf8')
lines = ['FIXTURE_SHA256=' + sha(fixture), 'SRTM_TYPE=valid HEIGHT=321 SOURCE=SRTM', 'REQUESTED_ALL_STREAMS_HZ=4',
         'FIXTURE_REPORT_MATCH=True', 'RETRY_OBSERVATION_COMPLETE=True']
assert all(line in log for line in lines) and (out / 'probe-exit.txt').read_text().strip() == '0'
paths = {'original_ardupilot': 'mission-planner-portable/MissionPlanner.ArduPilot.dll',
         'test_ardupilot': 'mission-planner-isolated/MissionPlanner.ArduPilot.dll',
         'original_utilities': 'mission-planner-portable/MissionPlanner.Utilities.dll',
         'test_utilities': 'mission-planner-isolated/MissionPlanner.Utilities.dll'}
hashes = {name: sha(root / path) for name, path in paths.items()}
assert hashes['original_ardupilot'] == hashes['test_ardupilot'] and hashes['original_utilities'] != hashes['test_utilities']
summary = {'scope': 'One dropped synthetic terrain block; patched Utilities; disposable SITL; finite observation',
           'relay': relay, 'fixture_sha256': sha(fixture), 'library_hashes': hashes,
           'probe_source_sha256': sha(out / 'probe-source.cs'), 'probe_exe_sha256': sha(out / 'probe.exe'),
           'probe_log_sha256': sha(out / 'probe.log'), 'relay_source_sha256': sha(out / 'relay-source.py'),
           'sent': sent, 'delivered': delivered, 'dropped': lost, 'matching_deliveries': matches,
           'matching_requests': matching_requests, 'reports': reports, 'heartbeats': heartbeats,
           'bad_data_fragments': {'input': bad_in, 'output': bad_out, 'dropped': bad_drop, 'downlink': bad_down},
           'verified_probe_lines': lines}
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print('Dropped first block 0;', len(matching_requests), 'matching requests;', len(matches), 'later matching deliveries')
