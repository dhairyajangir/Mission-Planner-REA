"""Independently decode two synthetic SRTM-to-SITL terrain attempts."""
import hashlib
import json
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
fixture = root / 'sitl-evidence/terrain-fixture-data/S36E149.hgt'
tile = fixture.read_bytes()
assert len(tile) == 1201 * 1201 * 2 and tile == (321).to_bytes(2, 'big', signed=True) * (1201 * 1201)
paths = {'original_ardupilot': 'mission-planner-portable/MissionPlanner.ArduPilot.dll',
         'test_ardupilot': 'mission-planner-isolated/MissionPlanner.ArduPilot.dll',
         'original_utilities': 'mission-planner-portable/MissionPlanner.Utilities.dll',
         'test_utilities': 'mission-planner-isolated/MissionPlanner.Utilities.dll',
         'original_mavlink': 'mission-planner-portable/MAVLink.dll', 'test_mavlink': 'mission-planner-isolated/MAVLink.dll'}
hashes = {name: sha(root / path) for name, path in paths.items()}
assert hashes['original_ardupilot'] == hashes['test_ardupilot'] and hashes['original_mavlink'] == hashes['test_mavlink']
assert hashes['original_utilities'] != hashes['test_utilities']
def decode(path):
    parser = ardupilotmega.MAVLink(None); parser.robust_parsing = True
    records, bad = [], 0
    for byte in path.read_bytes():
        msg = parser.parse_char(bytes([byte]))
        if msg is None: continue
        if msg.get_type() == 'BAD_DATA': bad += 1
        elif msg.get_type() in ('HEARTBEAT', 'TERRAIN_DATA', 'TERRAIN_REQUEST', 'TERRAIN_REPORT', 'TERRAIN_CHECK', 'REQUEST_DATA_STREAM'):
            item = msg.to_dict(); item['source'] = [msg.get_srcSystem(), msg.get_srcComponent()]; records.append(item)
    return records, bad
for case in ('terrain_fixture', 'terrain_fixture_stream'):
    out = root / 'sitl-evidence' / ('command-ack-' + case)
    relay = json.loads((out / 'relay-result.json').read_text())
    assert relay['case'] == case and relay['errors'] == [] and relay['closed_by'] == 'client'
    assert relay['buffered_bytes_at_close'] == 0
    for name, digest in relay['capture_sha256'].items(): assert sha(out / name) == digest
    up, bad_up = decode(out / 'to_sitl_output.bin'); down, bad_down = decode(out / 'to_client_output.bin')
    checks = [m for m in up if m['mavpackettype'] == 'TERRAIN_CHECK']
    data = [m for m in up if m['mavpackettype'] == 'TERRAIN_DATA']
    streams = [m for m in up if m['mavpackettype'] == 'REQUEST_DATA_STREAM']
    requests = [m for m in down if m['mavpackettype'] == 'TERRAIN_REQUEST' and m['source'] == [1, 1]]
    reports = [m for m in down if m['mavpackettype'] == 'TERRAIN_REPORT' and m['source'] == [1, 1]]
    heartbeats = [m for m in down if m['mavpackettype'] == 'HEARTBEAT' and m['source'] == [1, 1]]
    assert checks and all(m['lat'] == -353632610 and m['lon'] == 1491652300 for m in checks)
    assert reports and heartbeats and all(not (m['base_mode'] & 128) for m in heartbeats)
    log = (out / 'probe.log').read_text(encoding='utf8')
    lines = ['FIXTURE_SHA256=' + sha(fixture), 'SRTM_TYPE=valid HEIGHT=321 SOURCE=SRTM', 'SENT_TERRAIN_CHECK']
    if case == 'terrain_fixture':
        assert (out / 'probe-exit.txt').read_text().strip() == '1'
        assert not requests and not data and 'ERROR=System.Exception: terrain report timeout; requests=0' in log
        assert all(m['terrain_height'] == 0 for m in reports)
        lines += ['ERROR=System.Exception: terrain report timeout; requests=0']
    else:
        assert (out / 'probe-exit.txt').read_text().strip() == '0'
        assert any(m['req_stream_id'] == 0 and m['req_message_rate'] == 4 and m['start_stop'] == 1 for m in streams)
        assert len(data) == 40 and requests
        assert all(len(m['data']) == 16 and all(v == 321 for v in m['data']) for m in data)
        assert all(any(m['lat'] == r['lat'] and m['lon'] == r['lon'] and m['grid_spacing'] == r['grid_spacing'] and
                       (r['mask'] & (1 << m['gridbit'])) for r in requests) for m in data)
        assert any(m['lat'] == -353632610 and m['lon'] == 1491652300 and m['terrain_height'] == 321 and
                   m['pending'] == 16 and m['loaded'] == 40 for m in reports)
        lines += ['REQUESTED_ALL_STREAMS_HZ=4', 'FIXTURE_REPORT_MATCH=True']
    assert all(line in log for line in lines)
    result = {'scope': 'Synthetic flat HGT and disposable Copter SITL; test-patched Utilities; not real terrain',
              'case': case, 'relay': relay, 'fixture_sha256': sha(fixture), 'library_hashes': hashes,
              'probe_source_sha256': sha(out / 'probe-source.cs'), 'probe_exe_sha256': sha(out / 'probe.exe'),
              'probe_log_sha256': sha(out / 'probe.log'), 'streams': streams, 'checks': checks, 'data': data,
              'requests': requests, 'reports': reports, 'heartbeats': heartbeats,
              'bad_data_fragments': {'uplink': bad_up, 'downlink': bad_down}, 'verified_probe_lines': lines}
    (out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(case, len(data), 'terrain data frames;', len(requests), 'terrain requests')
