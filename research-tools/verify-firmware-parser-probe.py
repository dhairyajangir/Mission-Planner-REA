"""Independently compare synthetic APJ input with firmware-parser results."""
import base64
import hashlib
import json
from pathlib import Path
import zlib

run = Path(__file__).resolve().parent.parent / 'sitl-evidence/firmware-parser-probe'
fixtures = json.loads((run / 'fixtures.json').read_text())
lines = (run / 'probe.log').read_text(errors='replace').splitlines()
results = {}
for line in lines:
    if not line.startswith('RESULT|'):
        continue
    _, name, status, board, declared, length, value = line.split('|')
    results[name] = {'status': status, 'board_id': int(board), 'declared': int(declared),
                     'returned_length': int(length), 'returned_hex': value.lower()}
expected_hex = {'exact-4.apj': '41424344', 'short-image.apj': '4142434400000000',
                'exact-3.apj': '4142430000000000', 'exact-5.apj': '4142434445000000',
                'exact-7.apj': '414243444546470000000000'}
checks = []
for fixture in fixtures:
    path = run / fixture['file']
    data = json.loads(path.read_text())
    original = zlib.decompress(base64.b64decode(data['image']))
    observed = results[fixture['file']]
    checks.append({'file': fixture['file'], 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                   'declared': data['image_size'], 'actual_decompressed_bytes': len(original),
                   'observed': observed,
                   'passed': hashlib.sha256(path.read_bytes()).hexdigest() == fixture['sha256'] and
                             original.hex() == fixture['decompressed_hex'] and data['image_size'] == fixture['declared'] and
                             observed['status'] == 'OK' and observed['board_id'] == 9999 and
                             observed['declared'] == data['image_size'] and
                             observed['returned_hex'] == expected_hex[fixture['file']] and
                             observed['returned_length'] == len(bytes.fromhex(observed['returned_hex']))})
summary = {'scope': 'synthetic APJ-shaped fixtures, independent zlib readback; no firmware flash',
           'checks': checks, 'passed': len(checks) == 5 and all(x['passed'] for x in checks)}
(run / 'verification.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
if not summary['passed']:
    raise SystemExit(1)
