"""Validate isolated-metadata string-mode SITL captures and snapshot metadata."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega
source_metadata = root / 'mission-planner-runtime/isolated-data/ArduCopter.apm.pdef.xml'
metadata = source_metadata.read_bytes()
metadata_hash = hashlib.sha256(metadata).hexdigest()
params = [e for e in ET.fromstring(metadata).iter('param') if e.get('name') == 'ArduCopter:FLTMODE1']
assert len(params) == 1
options = {v.get('code'): (v.text or '').strip() for v in params[0].findall('./values/value')}
assert options['4'].lower() == 'guided'
orig_ap = root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll'
test_ap = root / 'mission-planner-isolated/MissionPlanner.ArduPilot.dll'
orig_util = root / 'mission-planner-portable/MissionPlanner.Utilities.dll'
test_util = root / 'mission-planner-isolated/MissionPlanner.Utilities.dll'
hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in
          [('original_ardupilot', orig_ap), ('test_ardupilot', test_ap), ('original_utilities', orig_util), ('test_utilities', test_util)]}
assert hashes['original_ardupilot'] == hashes['test_ardupilot'] and hashes['original_utilities'] != hashes['test_utilities']
def decode(path):
    parser = ardupilotmega.MAVLink(None); parser.robust_parsing = True
    found, bad = [], 0
    for byte in path.read_bytes():
        msg = parser.parse_char(bytes([byte]))
        if msg is None: continue
        if msg.get_type() == 'BAD_DATA': bad += 1; continue
        if msg.get_type() in ('HEARTBEAT', 'SET_MODE', 'COMMAND_LONG'):
            item = msg.to_dict(); item['source'] = [msg.get_srcSystem(), msg.get_srcComponent()]
            found.append(item)
    return found, bad
for case in ('string', 'string_verified'):
    out = root / 'sitl-evidence' / ('flight-mode-' + case)
    relay = json.loads((out / 'relay-result.json').read_text())
    assert relay['case'] == 'mode_' + case and relay['errors'] == [] and relay['closed_by'] == 'client'
    assert relay['buffered_bytes_at_close'] == 0 and relay['mode_packets'] == {
        'command_seen': 1, 'command_dropped': 0, 'legacy_seen': 2, 'legacy_dropped': 0}
    for name, digest in relay['capture_sha256'].items(): assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    up, up_bad = decode(out / 'to_sitl_output.bin'); down, down_bad = decode(out / 'to_client_output.bin')
    sent = [m for m in up if m['mavpackettype'] == 'SET_MODE' or (m['mavpackettype'] == 'COMMAND_LONG' and m['command'] == 176)]
    assert [m['mavpackettype'] for m in sent] == ['COMMAND_LONG', 'SET_MODE', 'SET_MODE']
    assert sent[0]['target_system'] == 1 and sent[0]['target_component'] == 1 and sent[0]['param1'] == 1 and sent[0]['param2'] == 4
    assert all(m['target_system'] == 1 and m['base_mode'] == 1 and m['custom_mode'] == 4 for m in sent[1:])
    heartbeats = [m for m in down if m['mavpackettype'] == 'HEARTBEAT' and m['source'] == [1, 1]]
    assert heartbeats and all((m['base_mode'] & 128) == 0 for m in heartbeats)
    assert any(m['custom_mode'] == 0 for m in heartbeats) and any(m['custom_mode'] == 4 for m in heartbeats)
    log = (out / 'probe.log').read_text(encoding='utf-16', errors='replace')
    lines = ['COPTER_METADATA_SHA256=' + metadata_hash, 'OPEN=True SELECTED=1:1',
             'INITIAL_MODE=0 ARMED=False FIRMWARE=ArduCopter2', 'TRANSLATED=True TARGET=1 BASE=1 CUSTOM=4',
             'INVALID_STRING_RETURNED', 'VALID_STRING_RETURNED', 'FINAL_MODE=4 ARMED=False']
    if case == 'string_verified': lines.append('PDEF_LOADED=True XML_MATCH=True VALUES_NONEMPTY=True VALUES_MATCH=True')
    assert all(line in log for line in lines)
    snapshot = out / 'ArduCopter.apm.pdef.xml'
    if snapshot.exists() and hashlib.sha256(snapshot.read_bytes()).hexdigest() != metadata_hash: raise ValueError('existing metadata differs')
    if not snapshot.exists(): shutil.copyfile(source_metadata, snapshot)
    summary = {'scope': 'Original ArduPilot assembly with test-patched Utilities data path; disarmed SITL',
               'case': case, 'relay': relay, 'library_hashes': hashes, 'metadata_sha256': metadata_hash,
               'metadata_guided_option': options['4'], 'metadata_reflection_checked': case == 'string_verified',
               'sent': sent, 'heartbeats': heartbeats, 'bad_data_fragments': {'uplink': up_bad, 'downlink': down_bad},
               'verified_probe_lines': lines}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(case, 'three mode packets; disarmed GUIDED heartbeat; metadata', metadata_hash)
