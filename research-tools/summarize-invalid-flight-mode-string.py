"""Independently decode the captured invalid-name Copter mode test."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega

out = root / 'sitl-evidence/flight-mode-string_invalid'
relay = json.loads((out / 'relay-result.json').read_text())
assert relay['case'] == 'mode_string_invalid' and relay['errors'] == []
assert relay['closed_by'] == 'client' and relay['buffered_bytes_at_close'] == 0
assert relay['mode_packets'] == {'command_seen': 0, 'command_dropped': 0, 'legacy_seen': 0, 'legacy_dropped': 0}
for name, digest in relay['capture_sha256'].items():
    assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest

def decode(path):
    parser = ardupilotmega.MAVLink(None)
    parser.robust_parsing = True
    found, bad = [], 0
    for b in path.read_bytes():
        msg = parser.parse_char(bytes([b]))
        if msg is None:
            continue
        if msg.get_type() == 'BAD_DATA':
            bad += 1
        elif msg.get_type() in ('HEARTBEAT', 'SET_MODE', 'COMMAND_LONG'):
            item = msg.to_dict()
            item['source'] = [msg.get_srcSystem(), msg.get_srcComponent()]
            found.append(item)
    return found, bad

up, bad_up = decode(out / 'to_sitl_output.bin')
down, bad_down = decode(out / 'to_client_output.bin')
sent = [m for m in up if m['mavpackettype'] == 'SET_MODE' or (m['mavpackettype'] == 'COMMAND_LONG' and m['command'] == 176)]
assert sent == []
heartbeats = [m for m in down if m['mavpackettype'] == 'HEARTBEAT' and m['source'] == [1, 1]]
assert heartbeats and all(m['custom_mode'] == 0 and not (m['base_mode'] & 128) for m in heartbeats)
source = root / 'mission-planner-runtime/isolated-data/ArduCopter.apm.pdef.xml'
digest = hashlib.sha256(source.read_bytes()).hexdigest()
snapshot = out / 'ArduCopter.apm.pdef.xml'
if snapshot.exists():
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == digest
else:
    shutil.copyfile(source, snapshot)
log = (out / 'probe.log').read_text(encoding='utf-8')
lines = ['COPTER_METADATA_SHA256=' + digest, 'OPEN=True SELECTED=1:1',
         'INITIAL_MODE=0 ARMED=False FIRMWARE=ArduCopter2', 'INVALID_STRING_RETURNED',
         'PDEF_LOADED=True XML_MATCH=True VALUES_NONEMPTY=True VALUES_MATCH=True', 'FINAL_MODE=0 ARMED=False HEARTBEATS=']
assert all(line in log for line in lines)
paths = {'original_ardupilot': 'mission-planner-portable/MissionPlanner.ArduPilot.dll',
         'test_ardupilot': 'mission-planner-isolated/MissionPlanner.ArduPilot.dll',
         'original_utilities': 'mission-planner-portable/MissionPlanner.Utilities.dll',
         'test_utilities': 'mission-planner-isolated/MissionPlanner.Utilities.dll'}
hashes = {name: hashlib.sha256((root / path).read_bytes()).hexdigest() for name, path in paths.items()}
assert hashes['original_ardupilot'] == hashes['test_ardupilot']
assert hashes['original_utilities'] != hashes['test_utilities']
summary = {'scope': 'Original ArduPilot assembly, patched Utilities data directory, disarmed Copter SITL; no UI',
           'relay': relay, 'library_hashes': hashes, 'metadata_sha256': digest, 'sent': sent,
           'heartbeats': heartbeats, 'bad_data_fragments': {'uplink': bad_up, 'downlink': bad_down},
           'verified_probe_lines': lines}
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print('No mode-setting packets;', len(heartbeats), 'disarmed STABILIZE heartbeats')
