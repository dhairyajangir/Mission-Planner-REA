"""Record bounded outcomes and hashes for synthetic JSON plan cases."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
folder = root / 'sitl-evidence/mission-plan-probe'
fixtures = json.loads((folder / 'fixtures.json').read_text())
log = (folder / 'probe.log').read_text(encoding='utf-16')
sections = {section.splitlines()[0]: section for section in log.split('CASE=')[1:]}
files = [folder / 'fixtures.json', folder / 'probe.log', root / 'research-tools/MissionPlanProbe.cs',
         root / 'research-tools/make-mission-plan-fixtures.py', root / 'mission-planner-portable/MissionPlanProbe.exe',
         root / 'mission-planner-portable/MissionPlanner.Utilities.dll']
hashes = {str(path.relative_to(root)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
checks = {
    'fixture_hashes': all(hashlib.sha256((folder / name).read_bytes()).hexdigest() == value['sha256'] and
                          (folder / name).stat().st_size == value['size'] for name, value in fixtures.items()),
    'simple_and_complex_flattened': 'COUNT=4' in sections['valid.plan'] and
        'ITEM=1 ID=16 FRAME=3 P1=2 P2=0 LAT=-35.3625 LON=149.166 ALT=25' in sections['valid.plan'] and
        'ITEM=2 ID=16 FRAME=3 P1=2 P2=0 LAT=-35.362 LON=149.167 ALT=30' in sections['valid.plan'] and
        'ITEM=3 ID=16 FRAME=3 P1=2 P2=0 LAT=-35.361 LON=149.168 ALT=35' in sections['valid.plan'],
    'missing_complex_exception': 'EXCEPTION=System.NullReferenceException' in sections['complex-missing.plan'],
    'short_params_exception': 'EXCEPTION=System.ArgumentOutOfRangeException' in sections['short-params.plan'],
}
summary = {'scope': 'Synthetic JSON plan fixtures in a library harness; not GUI error handling',
           'sha256': hashes, 'checks': checks, 'passed': all(checks.values())}
(folder / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
if not summary['passed']:
    raise SystemExit(1)
