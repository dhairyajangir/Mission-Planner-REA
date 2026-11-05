"""Summarize GPS instance zero altitude in the captured DataFlash log."""
import json
from pathlib import Path
import sys

run = Path(__file__).resolve().parent
base = run.parent
sys.path.insert(0, str(base / 'python'))
from pymavlink import mavutil

reader = mavutil.mavlink_connection(str(base / 'nonempty-log-probe/downloaded.bin'))
values = []
while True:
    msg = reader.recv_match(type='GPS')
    if msg is None:
        break
    if getattr(msg, 'I', None) == 0:
        values.append(float(msg.Alt))
reader.close()
result = {'scope': 'pymavlink parse, GPS instance 0 only; does not verify all plotted coordinates',
          'samples': len(values), 'minimum_m': min(values) if values else None,
          'maximum_m': max(values) if values else None, 'last_m': values[-1] if values else None}
(run / 'gps-altitude-summary.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
