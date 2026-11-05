"""Decode legacy fence point attempts against two Copter simulator versions."""
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
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
paths = {'ardupilot': 'mission-planner-portable/MissionPlanner.ArduPilot.dll',
         'utilities': 'mission-planner-portable/MissionPlanner.Utilities.dll',
         'mavlink': 'mission-planner-portable/MAVLink.dll', 'valuetuple': 'mission-planner-portable/System.ValueTuple.dll'}
hashes = {name: sha(root / path) for name, path in paths.items()}
def decode(path):
    parser = ardupilotmega.MAVLink(None); parser.robust_parsing = True
    found, bad = [], 0
    for byte in path.read_bytes():
        msg = parser.parse_char(bytes([byte]))
        if msg is None: continue
        if msg.get_type() == 'BAD_DATA': bad += 1
        elif msg.get_type() in ('HEARTBEAT', 'AUTOPILOT_VERSION', 'FENCE_POINT', 'FENCE_FETCH_POINT', 'PARAM_VALUE', 'PARAM_SET', 'STATUSTEXT'):
            item = msg.to_dict(); item['source'] = [msg.get_srcSystem(), msg.get_srcComponent()]; found.append(item)
    return found, bad
def distance(lat1, lon1, lat2, lon2):
    a = math.sin(math.radians(lat2-lat1)/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(math.radians(lon2-lon1)/2)**2
    return 2 * 6371000 * math.asin(math.sqrt(a))
expected = [(-35.363261,149.165230), (-35.364,149.164), (-35.362,149.164), (-35.363,149.167), (-35.364,149.164)]
for case in ('fence_legacy', 'fence_legacy_retry', 'fence_legacy_release'):
    out = root / 'sitl-evidence' / ('command-ack-' + case)
    relay = json.loads((out / 'relay-result.json').read_text())
    binary = root / ('sitl-evidence/arducopter' if case == 'fence_legacy_release' else 'sitl-evidence/archive-built/arducopter')
    assert relay['case'] == case and relay['binary_sha256'] == sha(binary)
    assert relay['errors'] == [] and relay['closed_by'] == 'client' and relay['buffered_bytes_at_close'] == 0
    for name, digest in relay['capture_sha256'].items(): assert sha(out / name) == digest
    up, bad_up = decode(out / 'to_sitl_output.bin'); down, bad_down = decode(out / 'to_client_output.bin')
    points = [m for m in up if m['mavpackettype'] == 'FENCE_POINT']
    fetches = [m for m in up if m['mavpackettype'] == 'FENCE_FETCH_POINT']
    received = [m for m in down if m['mavpackettype'] == 'FENCE_POINT' and m['source'] == [1, 1]]
    sets = [m for m in up if m['mavpackettype'] == 'PARAM_SET' and m['param_id'] in ('FENCE_TOTAL', 'FENCE_ACTION')]
    params = [m for m in down if m['mavpackettype'] == 'PARAM_VALUE' and m['source'] == [1, 1] and m['param_id'] in ('FENCE_TOTAL', 'FENCE_ACTION', 'FENCE_ENABLE')]
    versions = [m for m in down if m['mavpackettype'] == 'AUTOPILOT_VERSION' and m['source'] == [1, 1]]
    notices = [m for m in down if m['mavpackettype'] == 'STATUSTEXT' and m['source'] == [1, 1] and 'FENCE_FETCH_POINT' in m['text']]
    heartbeats = [m for m in down if m['mavpackettype'] == 'HEARTBEAT' and m['source'] == [1, 1]]
    assert versions and all(m['flight_sw_version'] == (0x040702ff if case == 'fence_legacy_release' else 0x04080000) for m in versions)
    assert heartbeats and all(not (m['base_mode'] & 128) for m in heartbeats)
    assert any(m['param_id'] == 'FENCE_ENABLE' and m['param_value'] == 0 for m in params)
    assert any(m['param_id'] == 'FENCE_TOTAL' and m['param_value'] == 5 for m in sets)
    assert any(m['param_id'] == 'FENCE_TOTAL' and m['param_value'] == 5 for m in params)
    log = (out / 'probe.log').read_text(encoding='utf8', errors='replace')
    lines = ['INITIAL_ENABLE=0 TOTAL=0', 'SET_TOTAL=True READBACK=5']
    if case != 'fence_legacy':
        assert any(m['param_id'] == 'FENCE_ACTION' and m['param_value'] == 0 for m in sets)
        lines += ['SET_ACTION_ZERO=True READBACK=0']
    if case == 'fence_legacy_release':
        assert (out / 'probe-exit.txt').read_text().strip() == '0'
        assert [m['idx'] for m in points] == list(range(5))
        assert [m['idx'] for m in fetches] == list(range(5)) * 2
        assert [m['idx'] for m in received] == list(range(5)) * 2
        assert any('deprecated' in m['text'].lower() for m in notices)
        assert all(m['count'] == 5 and distance(m['lat'], m['lng'], *expected[m['idx']]) < 5 for m in received)
        lines += ['LEGACY_ROUNDTRIP=True']
    else:
        assert (out / 'probe-exit.txt').read_text().strip() == '1'
        assert [m['idx'] for m in points] == [0] and [m['idx'] for m in fetches] == [0, 0, 0, 0] and not received
        lines += ['ERROR=System.TimeoutException: Timeout on read - getFencePoint']
    assert all(line in log for line in lines)
    summary = {'scope': 'Legacy point transfer in disposable disarmed Copter SITL; no rendered UI or enforcement',
               'relay': relay, 'binary_sha256': sha(binary), 'library_hashes': hashes, 'probe_source_sha256': sha(out / 'probe-source.cs'),
               'probe_exe_sha256': sha(out / 'probe.exe'), 'probe_log_sha256': sha(out / 'probe.log'), 'points': points,
               'fetches': fetches, 'received': received, 'sets': sets, 'params': params, 'versions': versions,
               'heartbeats': heartbeats, 'notices': notices, 'bad_data_fragments': {'uplink': bad_up, 'downlink': bad_down}, 'verified_probe_lines': lines}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(case, 'points', len(points), 'fetches', len(fetches), 'responses', len(received))
