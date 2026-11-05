"""Extract flight-mode entry points from the existing REA managed index."""
import hashlib
import json
from pathlib import Path
import sqlite3
root = Path(__file__).resolve().parent.parent
index = root / 'mission-planner-binary-evidence/rea-supporting-index.sqlite'
binary = root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll'
tokens = ['0x06000490', '0x06000491', '0x06000492', '0x06000493', '0x060004ae', '0x060004af']
with sqlite3.connect(f'file:{index.as_posix()}?mode=ro', uri=True) as db:
    recorded = db.execute('SELECT sha256 FROM assemblies WHERE file=?', (binary.name,)).fetchone()[0]
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == recorded
    methods = []
    for token in tokens:
        row = db.execute('SELECT token,declaring_type,name,il_sha256,body_status FROM methods WHERE assembly=? AND token=?',
                         (binary.name, token)).fetchone()
        assert row and row[4] == 'present' and row[3]
        calls = db.execute('SELECT il_offset,opcode,target_name,target_declaring_type FROM calls '
                           'WHERE assembly=? AND caller_token=? ORDER BY il_offset', (binary.name, token)).fetchall()
        methods.append({'token': row[0], 'declaring_type': row[1], 'name': row[2], 'il_sha256': row[3],
                        'body_status': row[4], 'calls': [dict(zip(('il_offset','opcode','name','type'), c)) for c in calls]})
assert [m['name'] for m in methods] == ['setMode'] * 4 + ['translateMode'] * 2
target = root / 'mission-planner-binary-evidence/flight-mode-method-map.json'
if target.exists(): raise FileExistsError(target)
target.write_text(json.dumps({'scope': 'Build-local static REA method records; not runtime dispatch',
    'assembly_sha256': recorded, 'index_sha256': hashlib.sha256(index.read_bytes()).hexdigest(), 'methods': methods}, indent=2) + '\n')
print('mapped', len(methods), 'mode methods')
