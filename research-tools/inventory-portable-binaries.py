"""Inventory PE headers and hashes in the downloaded portable distribution.

CLI-directory presence is a bounded header observation, not validation that an
image loads or identification of all bundled artifacts.
"""
import hashlib
import json
from pathlib import Path
import struct

root = Path(__file__).resolve().parent.parent
dist = root / 'mission-planner-portable'
out = root / 'mission-planner-binary-evidence/portable-binary-inventory.json'
rows = []
for path in sorted(dist.rglob('*')):
    if not path.is_file() or path.suffix.lower() not in ('.dll', '.exe'):
        continue
    if path.name.startswith('MissionPlannerMavlinkProbe'):
        continue
    data = path.read_bytes()
    row = {'path': path.relative_to(dist).as_posix(), 'size': len(data),
           'sha256': hashlib.sha256(data).hexdigest(), 'classification': 'unknown'}
    try:
        if data[:2] != b'MZ' or len(data) < 64:
            raise ValueError('missing DOS header')
        pe = struct.unpack_from('<I', data, 0x3c)[0]
        if pe + 24 > len(data) or data[pe:pe+4] != b'PE\0\0':
            raise ValueError('missing PE header')
        machine, _, _, _, _, opt_size, _ = struct.unpack_from('<HHIIIHH', data, pe+4)
        opt = pe + 24
        magic = struct.unpack_from('<H', data, opt)[0]
        number_offset = {0x10b: 92, 0x20b: 108}[magic]
        directory_offset = {0x10b: 96, 0x20b: 112}[magic]
        if opt_size < directory_offset or opt + opt_size > len(data):
            raise ValueError('invalid optional header extent')
        count = struct.unpack_from('<I', data, opt + number_offset)[0]
        cli_rva = cli_size = 0
        if count > 14 and directory_offset + 15 * 8 <= opt_size:
            cli_rva, cli_size = struct.unpack_from('<II', data, opt + directory_offset + 14 * 8)
        row.update(machine=hex(machine), pe_magic=hex(magic), cli_rva=cli_rva, cli_size=cli_size,
                   classification='managed-candidate' if cli_rva and cli_size else 'native-or-other-pe')
    except (ValueError, KeyError, struct.error) as exc:
        row['issue'] = str(exc)
    rows.append(row)
out.write_text(json.dumps({'scope': 'portable ZIP DLL/EXE files; excludes local test harness',
                           'limitations': ['Header classification is not runtime loading or full dependency verification.'],
                           'files': rows}, indent=2) + '\n', encoding='utf-8')
counts = {}
for row in rows:
    counts[row['classification']] = counts.get(row['classification'], 0) + 1
print(json.dumps({'files': len(rows), 'counts': counts}, indent=2))
