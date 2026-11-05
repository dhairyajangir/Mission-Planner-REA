"""Validate the instrumented backstage page disposal capture."""
import hashlib
import json
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega
out = root / 'sitl-evidence/command-ack-calibration_page_close_retry'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
relay = json.loads((out / 'relay-result.json').read_text())
assert relay['case'] == 'calibration_page_close_retry' and relay['errors'] == [] and relay['closed_by'] == 'client'
assert relay['buffered_bytes_at_close'] == 0
for name, digest in relay['capture_sha256'].items(): assert sha(out / name) == digest
def decode(path):
    parser = ardupilotmega.MAVLink(None); parser.robust_parsing = True
    records = []
    for byte in path.read_bytes():
        msg = parser.parse_char(bytes([byte]))
        if msg is None or msg.get_type() not in ('COMMAND_LONG', 'COMMAND_ACK', 'HEARTBEAT', 'STATUSTEXT'): continue
        item = msg.to_dict(); item['source'] = [msg.get_srcSystem(), msg.get_srcComponent()]; records.append(item)
    return records
up = decode(out / 'to_sitl_output.bin'); down = decode(out / 'to_client_output.bin')
commands = [m for m in up if m['mavpackettype'] == 'COMMAND_LONG' and m['command'] in (241, 400)]
acks = [m for m in down if m['mavpackettype'] == 'COMMAND_ACK' and m['command'] in (241, 400)]
assert [(m['command'], m['param1']) for m in commands] == [(400, 1), (241, 0), (241, 0), (400, 0)]
assert [(m['command'], m['result']) for m in acks] == [(400, 0), (241, 4), (241, 4), (400, 0)]
assert all(m['source'] == [1, 1] for m in acks)
log = (out / 'probe.log').read_text(encoding='utf-8')
lines = ['ARMED_HEARTBEAT=True', 'SUBSCRIPTIONS_BEFORE_DEACTIVATE=2',
         'AFTER_DEACTIVATE_ACTIVE=False BUTTON_TEXT=Click when Done SUBSCRIPTIONS=2', 'SAME_CONTROL=True',
         'AFTER_REACTIVATE_ACTIVE=False BUTTON_TEXT=Click when Done SUBSCRIPTIONS=2',
         'AFTER_RESTART_ACTIVE=True BUTTON_TEXT=Click when Done SUBSCRIPTIONS=4', 'RESTART_ACK_RESULT=4', 'DISARM_RETURN=True',
         'AFTER_CLOSE_DISPOSED=True SUBSCRIPTIONS=4']
assert all(line in log for line in lines) and [log.index(line) for line in lines] == sorted(log.index(line) for line in lines)
assert (out / 'probe-exit.txt').read_text().strip() == '0' and 'ERROR=' not in log
assert sha(root / 'mission-planner-isolated/MissionPlanner.Controls.dll') == sha(root / 'mission-planner-portable/MissionPlanner.Controls.dll')
summary = {'scope': 'Unrendered BackstageView disposal; patched Utilities; worker disarm with message pump; disposable SITL',
           'relay': relay, 'commands': commands, 'acks': acks, 'verified_probe_lines': lines, 'probe_exit': 0,
           'library_sha256': sha(root / 'mission-planner-isolated/MissionPlanner.ArduPilot.dll'),
           'main_sha256': sha(root / 'mission-planner-isolated/MissionPlanner.exe'), 'controls_sha256': sha(root / 'mission-planner-isolated/MissionPlanner.Controls.dll'),
           'utilities_sha256': sha(root / 'mission-planner-isolated/MissionPlanner.Utilities.dll'),
           'probe_source_sha256': sha(out / 'probe-source.cs'), 'probe_exe_sha256': sha(out / 'probe.exe'),
           'log_sha256': sha(out / 'probe.log')}
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print('Disposed control remained target of four subscriptions before connection close')
