"""Compare parser type sequences, retaining a few mismatch examples."""
import itertools
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root.parent / 'python'))
from pymavlink import mavutil

reader = mavutil.mavlink_connection(str(root / 'downloaded.bin'))
def types():
    while True:
        message = reader.recv_match()
        if message is None:
            break
        yield message.get_type()

mismatches = []
count = 0
with (root / 'converted.log').open(encoding='ascii', errors='replace') as stream:
    for count, (expected, line) in enumerate(itertools.zip_longest(types(), stream), 1):
        actual = line.split(',', 1)[0] if line is not None else None
        if expected != actual:
            mismatches.append({'index_1based': count, 'pymavlink': expected, 'mission_planner': actual,
                               'text_prefix': line[:160].rstrip() if line else None})
reader.close()
result = {'records_compared': count, 'mismatch_count': len(mismatches), 'examples': mismatches[:10],
          'scope': 'Type name sequence comparison only; field values not compared.'}
(root / 'sequence-comparison.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
