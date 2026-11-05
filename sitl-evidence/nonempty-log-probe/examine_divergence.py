"""Capture the first type-name divergence without changing the source log."""
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root.parent / 'python'))
from pymavlink import mavutil

reader = mavutil.mavlink_connection(str(root / 'downloaded.bin'))
records = []
for index in range(1, 1668):
    msg = reader.recv_match()
    if msg is None:
        raise RuntimeError('log ended before divergence')
    if index >= 1661:
        records.append({'index_1based': index, 'type': msg.get_type(), 'fields': msg.to_dict()})
reader.close()
lines = []
with (root / 'converted.log').open(encoding='ascii', errors='replace') as stream:
    for index, line in enumerate(stream, 1):
        if 1661 <= index <= 1667:
            lines.append({'line_1based': index, 'text': line.rstrip()})
        if index >= 1667:
            break
result = {'pymavlink': records, 'converted_lines': lines,
          'scope': 'Local divergence context; values and parser behavior are not independently validated.'}
(root / 'divergence-context.json').write_text(json.dumps(result, indent=2, default=str) + '\n')
print(json.dumps(records[3], default=str))
