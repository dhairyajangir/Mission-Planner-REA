"""Compare a captured truncated MAG record with a zero-completed control."""
import hashlib
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
app = root.parent.parent / 'mission-planner-portable'
converter = app / 'MissionPlannerLogConvertProbe.exe'
data = (root / 'downloaded.bin').read_bytes()
fmt_prefix = bytes([0xA3, 0x95, 0x80, 113, 35]) + b'MAG\x00'
fmt_offset = data.find(fmt_prefix)
record_offset = data.rfind(bytes([0xA3, 0x95, 113]))
if fmt_offset < 0 or record_offset < 0 or len(data) - record_offset != 31:
    raise ValueError('expected MAG format or 31-byte final record not found')
fmt = data[fmt_offset:fmt_offset + 89]
partial = data[record_offset:]
results = {}
for name, record in [('partial', partial), ('completed', partial + bytes(4))]:
    input_path = root / f'mag-{name}-fixture.bin'
    output_path = root / f'mag-{name}-converted.log'
    transcript = root / f'mag-{name}-converter.log'
    if any(path.exists() for path in (input_path, output_path, transcript)):
        raise FileExistsError('refusing to overwrite earlier fixture')
    input_path.write_bytes(fmt + record)
    proc = subprocess.run([str(converter), str(input_path), str(output_path)], cwd=app,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
    transcript.write_bytes(proc.stdout)
    lines = output_path.read_text(errors='replace').splitlines() if output_path.exists() else []
    results[name] = {'exit_code': proc.returncode, 'record_bytes': len(record),
                     'input_sha256': hashlib.sha256(input_path.read_bytes()).hexdigest(), 'lines': lines}
summary = {'format_offset': fmt_offset, 'record_offset': record_offset, 'expected_record_bytes': 35,
           'results': results, 'outputs_equal': results['partial']['lines'] == results['completed']['lines'],
           'scope': 'One captured partial record and one synthetic zero-completed control.'}
(root / 'truncated-mag-reproduction.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
