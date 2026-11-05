"""Decode two armed-SITL calibration attempts, including the original failed probe."""
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
for case in ('calibration_armed', 'calibration_armed_observed'):
    out = root / 'sitl-evidence' / ('command-ack-' + case)
    relay = json.loads((out / 'relay-result.json').read_text())
    assert relay['case'] == case and relay['errors'] == [] and relay['closed_by'] == 'client'
    assert relay['buffered_bytes_at_close'] == 0
    for name, digest in relay['capture_sha256'].items(): assert sha(out / name) == digest
    up, bad_up = decode(out / 'to_sitl_output.bin'); down, bad_down = decode(out / 'to_client_output.bin')
    arm = [m for m in up if m['mavpackettype'] == 'COMMAND_LONG' and m['command'] == 400]
    expected_arm = [1] if case == 'calibration_armed' else [1, 0]
    assert [m['param1'] for m in arm] == expected_arm and all(m['param2'] == 21196 for m in arm)
    commands = [m for m in up if m['mavpackettype'] == 'COMMAND_LONG' and m['command'] == 241]
    assert len(commands) == 1 and [commands[0]['param' + str(i)] for i in range(1, 8)] == [0, 0, 0, 0, 1, 0, 0]
    ack = [m for m in down if m['mavpackettype'] == 'COMMAND_ACK' and m['command'] == 241]
    assert len(ack) == 1 and ack[0]['result'] == 4 and ack[0]['source'] == [1, 1]
    notice = [m for m in down if m['mavpackettype'] == 'STATUSTEXT' and 'Disarm to allow calibration' in m['text']]
    assert notice and all(m['source'] == [1, 1] for m in notice)
    hb = [m for m in down if m['mavpackettype'] == 'HEARTBEAT' and m['source'] == [1, 1]]
    assert hb and any(m['base_mode'] & 128 for m in hb)
    log = (out / 'probe.log').read_text(encoding='utf-8')
    lines = ['ARM_COMMAND_RETURN=True', 'ARMED_HEARTBEAT=True', 'PREFLIGHT_CALIBRATION_RETURN=True']
    if case == 'calibration_armed': lines += ['ERROR=System.Exception: armed calibration unexpectedly accepted']
    else: lines += ['PREFLIGHT_ACK_RESULT=4', 'DISARM_COMMAND_RETURN=True', 'FINAL_ARMED=False']
    assert all(line in log for line in lines) and [log.index(line) for line in lines] == sorted(log.index(line) for line in lines)
    if case.endswith('_observed'): assert (hb[-1]['base_mode'] & 128) == 0
    summary = {'scope': 'Forced arm in disposable SITL only; client returns before calibration ACK',
               'relay': relay, 'library_sha256': sha(root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll'),
               'arm_commands': arm, 'calibration_commands': commands, 'calibration_ack': ack,
               'notices': notice, 'heartbeats': hb, 'bad_data_fragments': {'uplink': bad_up, 'downlink': bad_down},
               'verified_probe_lines': lines}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(case, 'library returned true; SITL sent FAILED')
