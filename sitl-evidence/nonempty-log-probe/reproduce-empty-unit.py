"""Isolate a UNIT record from the captured log and compare an edited control."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess

root = Path(__file__).resolve().parent
project = root.parent.parent
app = project / 'mission-planner-portable'
converter = app / 'MissionPlannerLogConvertProbe.exe'
data = (root / 'downloaded.bin').read_bytes()
fmt_prefix = bytes([0xA3, 0x95, 0x80, 119, 76]) + b'UNIT'
fmt_offset = data.find(fmt_prefix)
unit = bytes([0xA3, 0x95, 119]) + struct.pack('<Q', 2459849) + bytes([45]) + bytes(64)
unit_offset = data.find(unit)
if fmt_offset < 0 or unit_offset < 0 or data.find(unit, unit_offset + 1) >= 0:
    raise ValueError('expected unique captured format and empty UNIT record not found')
fmt = data[fmt_offset:fmt_offset + 89]
control = unit[:12] + b'x' + unit[13:]
results = {}
for name, record in [('empty', unit), ('nonempty', control)]:
    input_path = root / f'unit-{name}-fixture.bin'
    output_path = root / f'unit-{name}-converted.log'
    transcript = root / f'unit-{name}-converter.log'
    if any(path.exists() for path in (input_path, output_path, transcript)):
        raise FileExistsError('refusing to overwrite an earlier fixture')
    input_path.write_bytes(fmt + record)
    proc = subprocess.run([str(converter), str(input_path), str(output_path)], cwd=app,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
    transcript.write_bytes(proc.stdout)
    lines = output_path.read_text(errors='replace').splitlines() if output_path.exists() else []
    results[name] = {'exit_code': proc.returncode, 'input_sha256': hashlib.sha256(input_path.read_bytes()).hexdigest(),
                     'lines': lines, 'bad_line_warning': b'Bad Binary log line 119' in proc.stdout}
summary = {'source_format_offset': fmt_offset, 'source_unit_offset': unit_offset,
           'fixture_bytes_differ': sum(a != b for a, b in zip(fmt + unit, fmt + control)),
           'results': results, 'scope': 'One captured UNIT record and one synthetic one-byte control.'}
(root / 'empty-unit-reproduction.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
