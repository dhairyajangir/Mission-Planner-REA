"""Record bounded observations from the synthetic parameter-file harness."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
folder = root / 'sitl-evidence/param-file-probe'
log = (folder / 'probe.log').read_text(encoding='utf-16')
saved = (folder / 'saved.param').read_text().splitlines()
names = ('normal.param', 'bad-excluded.param', 'indented-comment.param', 'bad-value.param', 'saved.param', 'probe.log')
files = [folder / name for name in names] + [root / 'research-tools/ParamFileProbe.cs',
        root / 'mission-planner-portable/ParamFileProbe.exe', root / 'mission-planner-portable/MissionPlanner.Utilities.dll']
hashes = {str(path.relative_to(root)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
checks = {
    'duplicate_last_wins': 'normal.param KEY=DUP VALUE=2' in log,
    'excluded_keys_not_loaded': 'normal.param COUNT=5' in log and 'normal.param KEY=FORMAT_VERSION' not in log and
        'normal.param KEY=SYS_NUM_RESETS' not in log,
    'comma_delimiter': 'normal.param KEY=DECIMAL_COMMA VALUE=1' in log,
    'nonfinite_parsed': 'normal.param KEY=NAN VALUE=NaN' in log,
    'excluded_invalid_still_errors': 'bad-excluded.param EXCEPTION=System.FormatException' in log,
    'indented_comment_errors': 'indented-comment.param EXCEPTION=System.FormatException' in log,
    'invalid_value_errors': 'bad-value.param EXCEPTION=System.FormatException' in log,
    'de_culture_save_and_load': 'SAVED CULTURE=de-DE' in log and 'SAVED_READBACK COUNT=2' in log and
        'SAVED_READBACK KEY=ALPHA VALUE=-0.125' in log and 'SAVED_READBACK KEY=BETA VALUE=12.5' in log and
        saved == ['ALPHA,-0.125', 'BETA,12.5', 'FORMAT_VERSION,120'],
}
summary = {'scope': 'Synthetic parameter files through distributed utility library; no GUI or vehicle write',
           'sha256': hashes, 'checks': checks, 'passed': all(checks.values())}
(folder / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
if not summary['passed']:
    raise SystemExit(1)
