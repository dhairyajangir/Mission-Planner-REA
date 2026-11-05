"""Read the captured DataFlash log with pymavlink; do not modify the log."""
import collections
import hashlib
import json
from pathlib import Path
import sys

folder = Path(__file__).resolve().parent
sys.path.insert(0, str(folder.parent / 'python'))
from pymavlink import mavutil

download = folder / 'downloaded.bin'
original = folder / 'logs' / '00000001.BIN'
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
counts = collections.Counter()
log = mavutil.mavlink_connection(str(download))
while True:
    msg = log.recv_match()
    if msg is None:
        break
    counts[msg.get_type()] += 1
log.close()
result = {'download_bytes': download.stat().st_size, 'original_bytes': original.stat().st_size,
          'download_sha256': digest(download), 'original_sha256': digest(original),
          'message_count': sum(counts.values()), 'message_types': dict(sorted(counts.items())),
          'scope': 'pymavlink DataFlash parser, not Mission Planner playback'}
result['byte_identical'] = result['download_bytes'] == result['original_bytes'] and result['download_sha256'] == result['original_sha256']
(folder / 'download-verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({key: result[key] for key in ('download_bytes', 'download_sha256', 'byte_identical', 'message_count')}))
