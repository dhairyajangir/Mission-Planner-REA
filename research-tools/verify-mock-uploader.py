"""Check synthetic inputs, mock bootloader transcript and captured programmed bytes."""
import base64
import hashlib
import json
from pathlib import Path
import zlib

run = Path(__file__).resolve().parent.parent / 'sitl-evidence/mock-uploader-probe-2'
manifest = json.loads((run / 'fixtures.json').read_text())
log = (run / 'probe.log').read_text(errors='replace')
checks = []
for item in manifest:
    source = run / item['file']
    payload = json.loads(source.read_text())
    actual = zlib.decompress(base64.b64decode(payload['image'], validate=True))
    written = (run / (item['file'] + '.programmed.bin')).read_bytes()
    target = actual + bytes(item['declared'] - len(actual))
    name = item['file']
    checks.append({'file': name, 'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                   'decompressed_length': len(actual), 'programmed_length': len(written),
                   'programmed_sha256': hashlib.sha256(written).hexdigest(),
                   'matches_decompressed_plus_zeros': written == target,
                   'passed': hashlib.sha256(source.read_bytes()).hexdigest() == item['sha256'] and
                             hashlib.sha256(actual).hexdigest() == item['decompressed_sha256'] and
                             len(actual) == item['actual'] and payload['image_size'] == item['declared'] and
                             written == target and
                             ('RESULT|' + name + '|matching|OK|writes=9|erased=True|rebooted=True|bytes=252|') in log and
                             ('RESULT|' + name + '|mismatch|Exception:Firmware not suitable') in log and
                             ('RESULT|' + name + '|too-small|Exception:Firmware image is too large') in log})
summary = {'scope': 'in-memory bootloader fake; no operating-system serial port or physical hardware',
           'checks': checks, 'passed': len(checks) == 2 and all(item['passed'] for item in checks)}
(run / 'verification.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
if not summary['passed']:
    raise SystemExit(1)
