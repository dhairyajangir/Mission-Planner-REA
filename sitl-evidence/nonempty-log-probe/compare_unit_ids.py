"""Compare UNIT IDs in the binary parser and converter output."""
from collections import Counter
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root.parent / 'python'))
from pymavlink import mavutil

reader = mavutil.mavlink_connection(str(root / 'downloaded.bin'))
binary = Counter()
unit_45 = []
while True:
    msg = reader.recv_match(type='UNIT')
    if msg is None:
        break
    binary[str(msg.Id)] += 1
    if msg.Id == 45:
        unit_45.append(msg.to_dict())
reader.close()
converted = Counter()
with (root / 'converted.log').open(encoding='ascii', errors='replace') as stream:
    for line in stream:
        if line.startswith('UNIT, '):
            converted[line.split(',', 3)[2].strip()] += 1
diff = {key: {'pymavlink': binary[key], 'mission_planner': converted[key]}
        for key in sorted(set(binary) | set(converted)) if binary[key] != converted[key]}
result = {'unit_id_count_differences': diff, 'pymavlink_unit_45': unit_45,
          'scope': 'UNIT ID counts only; does not diagnose converter exceptions or verify field values.'}
(root / 'unit-id-comparison.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
