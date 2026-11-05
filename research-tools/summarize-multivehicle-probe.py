"""Independently decode synthetic fixtures and check library parser observations."""
import hashlib
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'sitl-evidence/python'))
from pymavlink.dialects.v20 import ardupilotmega as mav

folder = root / 'sitl-evidence/multivehicle-parser-probe'
manifest = json.loads((folder / 'fixtures.json').read_text())
log = (folder / 'isolation.log').read_text(encoding='utf-16')
sections = {section.splitlines()[0]: section for section in log.split('CASE=')[1:]}
decoded = {}
for name, info in manifest.items():
    data = (folder / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != info['sha256'] or len(data) != info['size']:
        raise ValueError('fixture mismatch: ' + name)
    parser = mav.MAVLink(None)
    parser.robust_parsing = True
    messages, bad_reasons = [], []
    for b in data:
        msg = parser.parse_char(bytes([b]))
        if msg is None:
            continue
        if msg.get_type() == 'BAD_DATA':
            bad_reasons.append(str(msg.reason))
            continue
        row = {'type': msg.get_type(), 'system': msg.get_srcSystem(), 'component': msg.get_srcComponent()}
        if msg.get_type() == 'PARAM_VALUE':
            row.update({'name': str(msg.param_id).rstrip('\x00'), 'value': msg.param_value})
        messages.append(row)
    decoded[name] = {'messages': messages, 'bad_reasons': bad_reasons}
handshake_log = (folder / 'handshake.log').read_text(encoding='utf-16')
files = [folder / 'fixtures.json', folder / 'isolation.log', folder / 'handshake.log',
         root / 'research-tools/HandshakeSelectionProbe.cs', root / 'mission-planner-portable/HandshakeSelectionProbe.exe',
         root / 'research-tools/MultiVehicleParserProbe.cs',
         root / 'research-tools/make-multivehicle-fixtures.py', root / 'mission-planner-portable/MultiVehicleIsolationProbe.exe',
         root / 'mission-planner-portable/LiveSigningProbe.exe', root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll',
         root / 'mission-planner-portable/MAVLink.dll']
hashes = {str(path.relative_to(root)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
isolated_values = [row['value'] for row in decoded['param-isolation.bin']['messages'] if row['type'] == 'PARAM_VALUE']
checks = {
    'independent_frame_decode': [len(decoded[name]['messages']) for name in ('vehicle-first.bin', 'gcs-first.bin', 'bad-only.bin', 'param-isolation.bin')] == [4, 3, 0, 6] and
        all(len(decoded[name]['bad_reasons']) == 1 for name in ('vehicle-first.bin', 'bad-only.bin', 'param-isolation.bin')) and
        isolated_values == [12.5, 87.5, 42.0],
    'vehicle_first_selection': 'READ=3 LENGTH=17 SYS=1 COMP=100 VISIBLE=4 SELECTED=1:1 REMAINING=17' in sections['vehicle-first.bin'] and
        'BAD_SYSTEM_VISIBLE=False' in sections['vehicle-first.bin'],
    'gcs_first_selection': 'READ=2 LENGTH=17 SYS=2 COMP=1 VISIBLE=3 SELECTED=255:190 REMAINING=0' in sections['gcs-first.bin'],
    'bad_only_rejected': 'READ=0 LENGTH=0 SYS=0 COMP=0 VISIBLE=0 SELECTED=0:0 REMAINING=0' in sections['bad-only.bin'],
    'separate_parameter_values': all(token in sections['param-isolation.bin'] for token in
        ('PARAM=1:1 VALUE=12.5', 'PARAM=2:1 VALUE=87.5', 'PARAM=1:100 VALUE=42', 'SELECTED=1:1 VISIBLE=3')),
    'corrupt_parameter_rejected': 'READ=6 LENGTH=0 SYS=0 COMP=0 MSG=0 REMAINING=0' in sections['param-isolation.bin'],
    'timed_open_selected_vehicle': decoded['gcs-first.bin']['messages'][0]['system'] == 255 and
        'HB Selection 1-1 seen 2' in handshake_log and 'OPEN=True SELECTED=1:1 VISIBLE=3' in handshake_log and
        '255:190:GCS' in handshake_log,
    'timed_open_version_retries': all('getVersion Retry ' + value in handshake_log for value in ('3', '2', '1')),
}
summary = {'scope': 'Synthetic MAVLink 1 through in-memory library transport, including timed Open test; no UI, network or vehicles',
           'sha256': hashes, 'fixtures': manifest, 'decoded': decoded, 'checks': checks, 'passed': all(checks.values())}
(folder / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
if not summary['passed']:
    raise SystemExit(1)
