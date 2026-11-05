"""Decode the instrumented calibration lifecycle attempt and retained timeout."""
import hashlib
import json
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega
out = root / 'sitl-evidence/command-ack-calibration_lifecycle_observed'
relay = json.loads((out / 'relay-result.json').read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert relay['case'] == 'calibration_lifecycle_observed' and relay['errors'] == [] and relay['closed_by'] == 'client'
for name, digest in relay['capture_sha256'].items(): assert sha(out / name) == digest
def decode(path):
    p = ardupilotmega.MAVLink(None); p.robust_parsing = True
    found = []
    for b in path.read_bytes():
        m = p.parse_char(bytes([b]))
        if m is None or m.get_type() not in ('COMMAND_LONG', 'COMMAND_ACK', 'HEARTBEAT', 'STATUSTEXT'): continue
        item = m.to_dict(); item['source'] = [m.get_srcSystem(), m.get_srcComponent()]; found.append(item)
    return found
up = decode(out / 'to_sitl_output.bin'); down = decode(out / 'to_client_output.bin')
commands = [m for m in up if m['mavpackettype'] == 'COMMAND_LONG' and m['command'] in (241, 400)]
assert [(m['command'], m['param1']) for m in commands] == [(400, 1), (241, 0), (241, 0), (400, 0)]
assert all(m['param5'] == 1 for m in commands if m['command'] == 241)
acks = [m for m in down if m['mavpackettype'] == 'COMMAND_ACK' and m['command'] in (241, 400)]
assert [(m['command'], m['result']) for m in acks] == [(400, 0), (241, 4), (241, 4), (400, 0)]
assert all(m['source'] == [1, 1] for m in acks)
log = (out / 'probe.log').read_text(encoding='utf-8')
lines = ['ARMED_HEARTBEAT=True', 'AFTER_REJECTION_ACTIVE=True BUTTON_ENABLED=True BUTTON_TEXT=Click when Done LABEL=Disarm to allow calibration',
         'SUBSCRIPTIONS_BEFORE_DEACTIVATE=2', 'AFTER_DEACTIVATE_ACTIVE=False BUTTON_TEXT=Click when Done SUBSCRIPTIONS=2',
         'AFTER_REACTIVATE_ACTIVE=False BUTTON_TEXT=Click when Done SUBSCRIPTIONS=2',
         'AFTER_RESTART_ACTIVE=True BUTTON_TEXT=Click when Done SUBSCRIPTIONS=4', 'RESTART_ACK_RESULT=4']
assert all(line in log for line in lines) and [log.index(line) for line in lines] == sorted(log.index(line) for line in lines)
assert (out / 'probe-exit.txt').read_text().strip() == '124' and 'DISARM_RETURN=' not in log
result = {'scope': 'Direct unrendered control lifecycle; patched Utilities; disposable SITL; harness timeout',
          'relay': relay, 'commands': commands, 'acks': acks, 'verified_probe_lines': lines,
          'probe_exit': 124, 'library_sha256': sha(root / 'mission-planner-isolated/MissionPlanner.ArduPilot.dll'),
          'main_sha256': sha(root / 'mission-planner-isolated/MissionPlanner.exe'),
          'utilities_sha256': sha(root / 'mission-planner-isolated/MissionPlanner.Utilities.dll'),
          'probe_source_sha256': sha(out / 'probe-source.cs'), 'probe_exe_sha256': sha(out / 'probe.exe'),
          'log_sha256': sha(out / 'probe.log')}
(out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
print('Lifecycle retained two subscriptions; restart added two; disarm ACK captured; harness timed out')
