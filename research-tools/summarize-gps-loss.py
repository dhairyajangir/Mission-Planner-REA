"""Summarize transitions from a retained GPS-loss simulator result."""
import hashlib
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parent.parent
name = sys.argv[1] if len(sys.argv) > 1 else 'archive-copter-gps-loss'
if Path(name).name != name or name in ('.', '..'):
    raise ValueError('expected a single evidence directory name')
source = root / 'sitl-evidence' / name / 'results.json'
data = json.loads(source.read_text())
transitions = []
last = {}
for event in data['events']:
    kind = event['type']
    if kind == 'GPS_RAW_INT':
        value = (event['fix_type'], event['satellites_visible'])
    elif kind == 'HEARTBEAT':
        value = (event['mode'], event['armed'])
    elif kind == 'EKF_STATUS_REPORT':
        value = event['flags']
    elif kind in ('gps_disable_confirmed', 'gps_restore_confirmed'):
        transitions.append(event)
        continue
    elif kind == 'STATUSTEXT':
        transitions.append(event)
        continue
    else:
        continue
    if last.get(kind) != value:
        transitions.append(event)
        last[kind] = value
summary = {'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
           'scope': 'Message-arrival times relative to harness start, not exact fault or flight timing',
           'checks': data['checks'], 'transitions': transitions}
target = source.parent / 'transition-summary.json'
target.write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
