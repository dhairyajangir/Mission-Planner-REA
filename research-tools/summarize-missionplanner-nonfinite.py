"""Summarize the original Mission Planner library's local SITL probe."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
folder = root / 'sitl-evidence/missionplanner-nonfinite-probe'
log = (folder / 'probe.log').read_text(encoding='utf-16')
host = json.loads((folder / 'host-result.json').read_text())
files = [folder / name for name in ('probe.log', 'input.param', 'host-result.json', 'ready.json')]
files += [root / 'research-tools/MissionPlannerNonfiniteProbe.cs',
          root / 'mission-planner-portable/MissionPlannerNonfiniteProbe.exe',
          root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll',
          root / 'mission-planner-portable/MAVLink.dll']
hashes = {str(path.relative_to(root)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
checks = {'parsed_nan': 'PARSED_NAN=True' in log,
          'error_enum_absent': 'PARAM_ERROR_ENUM_PRESENT=False' in log,
          'connected_and_baseline': 'OPEN=True' in log and 'BEFORE=0' in log,
          'unknown_id_and_retries': log.count('Unknown Packet 345') == 4 and
              all('setParam Retry ' + value in log for value in ('3', '2', '1')),
          'timeout_and_unchanged': 'NONFINITE_EXCEPTION=System.TimeoutException' in log and 'AFTER_NONFINITE=0' in log,
          'finite_and_restore': all(value in log for value in ('FINITE_SET=True', 'FINITE_READBACK=1',
                                                                'RESTORE_SET=True', 'RESTORE_READBACK=0')),
          'host_clean': host['done_marker_seen'] and not host['errors'] and host['port'] == 6900}
summary = {'scope': 'Original library and synthetic file against disposable source-built localhost SITL; not GUI or hardware',
           'binary_sha256': host['binary_sha256'], 'sha256': hashes, 'checks': checks, 'passed': all(checks.values())}
(folder / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
if not summary['passed']:
    raise SystemExit(1)
