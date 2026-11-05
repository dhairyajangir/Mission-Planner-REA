"""Independently compare calibration output to raw readback after SITL reboot."""
import hashlib
import json
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega
run = root / 'sitl-evidence/command-ack-calibration_full'
out = root / 'sitl-evidence/accel-calibration-reboot'
result = json.loads((out / 'result.json').read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert result['errors'] == []
assert result['binary_sha256'] == sha(root / 'sitl-evidence/archive-built/arducopter')
assert result['original_capture_sha256'] == sha(run / 'to_client_output.bin')
assert result['source_storage_sha256'] == result['copied_storage_sha256'] == sha(out / 'eeprom-before.bin') == sha(run / 'eeprom.bin')
assert result['post_shutdown_storage_sha256'] == sha(out / 'eeprom.bin')
assert result['downlink_sha256'] == sha(out / 'downlink.bin')
names = set(result['expected_from_prior_capture'])
assert len(names) == 14 and names == set(result['observed_after_reboot'])
def decode(path):
    p = ardupilotmega.MAVLink(None); p.robust_parsing = True
    for b in path.read_bytes():
        m = p.parse_char(bytes([b]))
        if m is not None and m.get_type() != 'BAD_DATA': yield m
expected = {}; after_six = False; completed = False
for m in decode(run / 'to_client_output.bin'):
    if m.get_type() == 'COMMAND_LONG' and m.command == 42429 and m.param1 == 6: after_six = True
    elif after_six and m.get_type() == 'PARAM_VALUE' and m.param_id in names and (m.get_srcSystem(), m.get_srcComponent()) == (1, 1): expected[m.param_id] = m.param_value
    elif after_six and m.get_type() == 'STATUSTEXT' and 'Calibration successful' in m.text: completed = True; break
observed = {}
heartbeats = []
for m in decode(out / 'downlink.bin'):
    if (m.get_srcSystem(), m.get_srcComponent()) != (1, 1): continue
    if m.get_type() == 'PARAM_VALUE' and m.param_id in names: observed[m.param_id] = m.param_value
    elif m.get_type() == 'HEARTBEAT': heartbeats.append(m.to_dict())
assert completed and expected == result['expected_from_prior_capture']
assert observed == result['observed_after_reboot'] == expected
assert heartbeats and all(not (m['base_mode'] & 128) for m in heartbeats)
summary = {'scope': 'Disarmed Copter SITL reboot from a copy of calibration-run storage; no physical sensor',
           'parameter_values': observed, 'source_capture_sha256': result['original_capture_sha256'],
           'readback_capture_sha256': result['downlink_sha256'], 'original_storage_sha256': result['source_storage_sha256'],
           'reboot_storage_after_shutdown_sha256': result['post_shutdown_storage_sha256'],
           'binary_sha256': result['binary_sha256'], 'readback_source_sha256': sha(out / 'readback-source.py'),
           'heartbeat_count': len(heartbeats)}
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print('Raw captures agree for', len(observed), 'calibration values across a SITL reboot')
