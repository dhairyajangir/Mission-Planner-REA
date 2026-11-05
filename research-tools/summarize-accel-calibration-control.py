"""Decode the instrumented WinForms control's armed calibration attempts."""
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
paths = {'original_main': root / 'mission-planner-portable/MissionPlanner.exe',
         'test_main': root / 'mission-planner-isolated/MissionPlanner.exe',
         'original_library': root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll',
         'test_library': root / 'mission-planner-isolated/MissionPlanner.ArduPilot.dll',
         'original_utilities': root / 'mission-planner-portable/MissionPlanner.Utilities.dll',
         'test_utilities': root / 'mission-planner-isolated/MissionPlanner.Utilities.dll'}
hashes = {name: sha(path) for name, path in paths.items()}
assert hashes['original_main'] == hashes['test_main']
assert hashes['original_library'] == hashes['test_library']
assert hashes['original_utilities'] != hashes['test_utilities']
def decode(path):
    p = ardupilotmega.MAVLink(None); p.robust_parsing = True
    records, bad = [], 0
    for b in path.read_bytes():
        m = p.parse_char(bytes([b]))
        if m is None: continue
        if m.get_type() == 'BAD_DATA': bad += 1
        elif m.get_type() in ('HEARTBEAT', 'COMMAND_LONG', 'COMMAND_ACK', 'STATUSTEXT'):
            item = m.to_dict(); item['source'] = [m.get_srcSystem(), m.get_srcComponent()]; records.append(item)
    return records, bad
for case in ('calibration_control', 'calibration_control_retry'):
    out = root / 'sitl-evidence' / ('command-ack-' + case)
    relay = json.loads((out / 'relay-result.json').read_text())
    assert relay['case'] == case and relay['errors'] == [] and relay['closed_by'] == 'client' and relay['buffered_bytes_at_close'] == 0
    for name, digest in relay['capture_sha256'].items(): assert sha(out / name) == digest
    up, bad_up = decode(out / 'to_sitl_output.bin'); down, bad_down = decode(out / 'to_client_output.bin')
    sent = [m for m in up if m['mavpackettype'] == 'COMMAND_LONG' and m['command'] in (241, 42429)]
    assert [m['command'] for m in sent] == ([241] if case == 'calibration_control' else [241, 42429])
    assert sent[0]['param5'] == 1 and sent[0]['target_system'] == 1 and sent[0]['target_component'] == 1
    if len(sent) == 2: assert sent[1]['param1'] == 0 and sent[1]['target_system'] == 0 and sent[1]['target_component'] == 0
    acks = [m for m in down if m['mavpackettype'] == 'COMMAND_ACK' and m['command'] in (241, 42429)]
    assert [m['command'] for m in acks] == [m['command'] for m in sent]
    assert all(m['result'] == 4 and m['source'] == [1, 1] for m in acks)
    notices = [m for m in down if m['mavpackettype'] == 'STATUSTEXT' and 'Disarm to allow calibration' in m['text']]
    assert notices and all(m['source'] == [1, 1] for m in notices)
    hb = [m for m in down if m['mavpackettype'] == 'HEARTBEAT' and m['source'] == [1, 1]]
    assert hb and any(m['base_mode'] & 128 for m in hb)
    log = (out / 'probe.log').read_text(encoding='utf-8')
    lines = ['ARM_COMMAND_RETURN=True', 'ARMED_HEARTBEAT=True', 'BEFORE_ACTIVE=False BUTTON_ENABLED=True BUTTON_TEXT=Calibrate Accel',
             'AFTER_CLICK_ACTIVE=True BUTTON_ENABLED=True BUTTON_TEXT=Click when Done', 'SAW_FAILED_ACK=True SAW_NOTICE=True',
             'AFTER_REJECTION_ACTIVE=True BUTTON_ENABLED=True BUTTON_TEXT=Click when Done LABEL=Disarm to allow calibration']
    if case.endswith('_retry'): lines += ['SECOND_CLICK_ACTIVE=True BUTTON_TEXT=Click when Done', 'POSITION_ACK_RESULT=4']
    lines += ['DISARM_RETURN=True']
    assert all(line in log for line in lines) and [log.index(line) for line in lines] == sorted(log.index(line) for line in lines)
    result = {'scope': 'Direct reflection on unrendered control; patched Utilities; forced-arm disposable simulator only',
              'relay': relay, 'assembly_hashes': hashes, 'probe_source_sha256': sha(out / 'probe-source.cs'),
              'probe_exe_sha256': sha(out / 'probe.exe'), 'commands': sent, 'acks': acks, 'notices': notices,
              'heartbeats': hb, 'bad_data_fragments': {'uplink': bad_up, 'downlink': bad_down}, 'verified_probe_lines': lines}
    (out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(case, 'control remained in calibration state after failed ACK')
