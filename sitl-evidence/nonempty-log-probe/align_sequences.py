"""Find short sequence shifts between pymavlink and converter type names."""
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root.parent / 'python'))
from pymavlink import mavutil

reader = mavutil.mavlink_connection(str(root / 'downloaded.bin'))
source = []
while True:
    msg = reader.recv_match()
    if msg is None:
        break
    source.append(msg.get_type())
reader.close()
with (root / 'converted.log').open(encoding='ascii', errors='replace') as stream:
    converted = [line.split(',', 1)[0] for line in stream]
i = j = 0
edits = []
while i < len(source) and j < len(converted):
    if source[i] == converted[j]:
        i += 1
        j += 1
        continue
    candidates = []
    # Repeated message types can make this heuristic ambiguous; require 12 names in a row.
    for a in range(0, 31):
        for b in range(0, 31):
            if a == b == 0 or i + a + 12 > len(source) or j + b + 12 > len(converted):
                continue
            if source[i+a:i+a+12] == converted[j+b:j+b+12]:
                candidates.append((a+b, a, b))
    if not candidates:
        edits.append({'source_index_1based': i+1, 'converted_index_1based': j+1, 'unresolved': True})
        break
    _, a, b = min(candidates)
    edits.append({'source_index_1based': i+1, 'converted_index_1based': j+1,
                  'pymavlink_only': source[i:i+a], 'mission_planner_only': converted[j:j+b]})
    i += a
    j += b
result = {'aligned_source_records': i, 'aligned_converted_lines': j, 'source_records': len(source),
          'converted_lines': len(converted), 'candidate_edits': edits,
          'pymavlink_unaligned_tail': source[i:], 'mission_planner_unaligned_tail': converted[j:],
          'scope': 'Heuristic type-name alignment only; duplicate names can make alignment ambiguous.'}
(root / 'sequence-alignment.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
