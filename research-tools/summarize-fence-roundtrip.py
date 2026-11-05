"""Decode typed mission/fence roundtrip and retain the initial failed assertion."""
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
paths = {'ardupilot': 'mission-planner-portable/MissionPlanner.ArduPilot.dll',
         'utilities': 'mission-planner-portable/MissionPlanner.Utilities.dll',
         'mavlink': 'mission-planner-portable/MAVLink.dll'}
hashes = {name: sha(root / path) for name, path in paths.items()}
def decode(path):
    p = ardupilotmega.MAVLink(None); p.robust_parsing = True
    found, bad = [], 0
    for byte in path.read_bytes():
        msg = p.parse_char(bytes([byte]))
        if msg is None: continue
        if msg.get_type() == 'BAD_DATA': bad += 1
        elif msg.get_type().startswith('MISSION_') or msg.get_type() == 'HEARTBEAT':
            item = msg.to_dict(); item['source'] = [msg.get_srcSystem(), msg.get_srcComponent()]; found.append(item)
    return found, bad
for case in ('fence_roundtrip', 'fence_roundtrip_retry', 'fence_roundtrip_stable', 'fence_highlevel'):
    out = root / 'sitl-evidence' / ('command-ack-' + case)
    relay = json.loads((out / 'relay-result.json').read_text())
    assert relay['case'] == case and relay['errors'] == [] and relay['closed_by'] == 'client' and relay['buffered_bytes_at_close'] == 0
    for name, digest in relay['capture_sha256'].items(): assert sha(out / name) == digest
    up, bad_up = decode(out / 'to_sitl_output.bin'); down, bad_down = decode(out / 'to_client_output.bin')
    sent = [m for m in up if m['mavpackettype'] == 'MISSION_ITEM_INT']
    counts = [m for m in up if m['mavpackettype'] == 'MISSION_COUNT']
    received = [m for m in down if m['mavpackettype'] == 'MISSION_ITEM_INT' and m['source'] == [1, 1]]
    acks = [m for m in down if m['mavpackettype'] == 'MISSION_ACK' and m['source'] == [1, 1]]
    requests = [m for m in down if m['mavpackettype'] in ('MISSION_REQUEST', 'MISSION_REQUEST_INT') and m['source'] == [1, 1]]
    heartbeats = [m for m in down if m['mavpackettype'] == 'HEARTBEAT' and m['source'] == [1, 1]]
    log = (out / 'probe.log').read_text(encoding='utf8')
    assert heartbeats and all(not (m['base_mode'] & 128) for m in heartbeats)
    assert [(m['mission_type'], m['count']) for m in counts][:1] == [(0, 2)]
    assert [(m['seq'], m['command']) for m in sent if m['mission_type'] == 0] == [(0, 16), (1, 16)]
    assert 'READ=MISSION:0:16:0:0:0:0' in log
    if case == 'fence_roundtrip':
        assert (out / 'probe-exit.txt').read_text().strip() == '1'
        assert 'ERROR=System.Exception: item mismatch MISSION:0' in log
        assert all(m['mission_type'] == 0 for m in counts + sent)
        assert any(m['seq'] == 0 and m['x'] == 0 and m['y'] == 0 for m in received)
        lines = ['READ=MISSION:0:16:0:0:0:0', 'ERROR=System.Exception: item mismatch MISSION:0']
    else:
        assert (out / 'probe-exit.txt').read_text().strip() == '0'
        assert [(m['mission_type'], m['count']) for m in counts] == [(0, 2), (1, 4)]
        fence = [m for m in sent if m['mission_type'] == 1]
        read_fence = [m for m in received if m['mission_type'] == 1]
        expected = [(0, 5001, 3, -353640000, 1491639999), (1, 5001, 3, -353620000, 1491639999),
                    (2, 5001, 3, -353630000, 1491670000), (3, 5004, 25, -353630000, 1491658000)]
        assert [(m['seq'], m['command'], m['param1'], m['x'], m['y']) for m in fence] == expected
        assert [(m['seq'], m['command'], m['param1'], m['x'], m['y']) for m in read_fence] == expected
        assert all(m['autocontinue'] == 1 for m in fence) and all(m['autocontinue'] == 0 for m in read_fence)
        assert [(m['mission_type'], m['type']) for m in acks] == [(0, 0), (1, 0)]
        assert [(m['mission_type'], m['seq']) for m in requests] == [(0, 0), (0, 1), (1, 0), (1, 1), (1, 2), (1, 3)]
        mission_read = [m for m in received if m['mission_type'] == 0]
        assert len(mission_read) == 4 and mission_read[:2] == mission_read[2:]
        assert mission_read[0]['x'] == mission_read[0]['y'] == 0
        assert (mission_read[1]['x'], mission_read[1]['y'], mission_read[1]['z']) == (-353630000, 1491655000, 20)
        lines = ['COUNT=FENCE:4', 'HIGHLEVEL_FENCE_ROUNDTRIP=True MISSION_PRESERVED=True'] if case == 'fence_highlevel' else ['COUNT=FENCE:4', 'MISSION_PRESERVED=True FENCE_ROUNDTRIP=True']
        if case == 'fence_roundtrip_stable': lines.append('POST_UPLOAD_WAIT_SECONDS=12')
        if case == 'fence_highlevel':
            assert 'UPLOAD_COMPLETE=MISSION' in log and 'UPLOAD_COMPLETE=FENCE' in log and 'CAPABILITIES=64495 REQUIRED=16388' in log
        else:
            assert all('UPLOAD=FENCE:' + str(i) + ':MAV_MISSION_ACCEPTED' in log for i in range(4))
    assert all(line in log for line in lines)
    summary = {'scope': 'Original Mission Planner library; typed mission and fence in disposable Copter SITL; no UI or flight',
               'relay': relay, 'library_hashes': hashes, 'probe_source_sha256': sha(out / 'probe-source.cs'),
               'probe_exe_sha256': sha(out / 'probe.exe'), 'probe_log_sha256': sha(out / 'probe.log'),
               'sent': sent, 'counts': counts, 'received': received, 'acks': acks, 'requests': requests,
               'heartbeats': heartbeats, 'bad_data_fragments': {'uplink': bad_up, 'downlink': bad_down},
               'verified_probe_lines': lines}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(case, 'sent', len(sent), 'mission items; received', len(received))
