"""Record hashes and bounded outcomes from the local mission-file harness."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
folder = root / 'sitl-evidence/mission-file-probe'
log = (folder / 'probe.log').read_text(encoding='utf-16')
mission = json.loads((folder / 'generated.mission').read_text())
files = [folder / name for name in ('normal.waypoints', 'no-home.waypoints', 'flag-variant.waypoints',
                                    'generated.mission', 'probe.log')]
files += [root / 'mission-planner-portable/MissionFileProbe.exe',
          root / 'mission-planner-portable/MissionPlanner.Utilities.dll',
          root / 'research-tools/MissionFileProbe.cs']
hashes = {str(path.relative_to(root)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
          for path in files}
checks = {
    'text_two_items': 'TEXT COUNT=2' in log and 'TEXT ITEM=1 ID=16 FRAME=3 P1=2 LAT=-35.3625 LON=149.166 ALT=25' in log,
    'missing_home_inserted': 'NO_HOME COUNT=2' in log and 'NO_HOME ITEM=0 ID=0 FRAME=0 P1=0 LAT=0 LON=0 ALT=0' in log,
    'flags_not_represented_in_dump': 'FLAG_VARIANT ITEM=1 ID=16 FRAME=3 P1=2 LAT=-35.3625 LON=149.166 ALT=25' in log,
    'generated_item_type_null': len(mission['mission']['items']) == 1 and mission['mission']['items'][0]['type'] is None,
    'generated_readback_only_home': 'JSON_READBACK COUNT=1' in log,
    'simple_item_control_recovers_waypoint': 'JSON_SIMPLE_CONTROL COUNT=2' in log and
        'JSON_SIMPLE_CONTROL ITEM=1 ID=16 FRAME=3 P1=2 LAT=-35.3625 LON=149.166 ALT=25' in log,
}
result = {'scope': 'Synthetic local files through distributed library; not a GUI or vehicle test',
          'sha256': hashes, 'checks': checks, 'passed': all(checks.values())}
(folder / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
if not result['passed']:
    raise SystemExit(1)
