"""Collect selected REA method and call records for the calibration control."""
import hashlib
import json
from pathlib import Path
import sqlite3
root = Path(__file__).resolve().parent.parent
index = root / 'mission-planner-binary-evidence/rea-main-index.sqlite'
exe = root / 'mission-planner-portable/MissionPlanner.exe'
tokens = ['0x06000d3a', '0x06000d3b', '0x06000d3d', '0x06000d3e']
with sqlite3.connect(f'file:{index.as_posix()}?mode=ro', uri=True) as c:
    provenance = c.execute('select * from provenance').fetchone()[0]
    methods = []
    for token in tokens:
        row = c.execute('select declaring_type,name,il_sha256,body_status from methods where token=?', (token,)).fetchone()
        assert row is not None and row[0].endswith('ConfigAccelerometerCalibration') and row[3] == 'present'
        calls = [dict(zip(('il_offset', 'opcode', 'target_token', 'name', 'type'), call)) for call in c.execute(
            'select il_offset,opcode,target_token,target_name,target_declaring_type from calls where caller_token=? order by il_offset', (token,))]
        methods.append(dict(zip(('declaring_type', 'name', 'il_sha256', 'body_status'), row), token=token, calls=calls))
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(exe) == provenance
result = {'scope': 'REA static method records and call references; no runtime UI execution implied',
          'assembly_sha256': sha(exe), 'index_sha256': sha(index), 'methods': methods}
out = root / 'mission-planner-binary-evidence/accel-calibration-method-map.json'
out.write_text(json.dumps(result, indent=2) + '\n')
print('Mapped', len(methods), 'REA calibration methods')
