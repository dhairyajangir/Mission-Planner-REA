"""Extract command entry points and async state machines from the REA index."""
import hashlib
import json
from pathlib import Path
import sqlite3

root = Path(__file__).resolve().parent.parent
database = root / 'mission-planner-binary-evidence/rea-supporting-index.sqlite'
binary = root / 'mission-planner-portable/MissionPlanner.ArduPilot.dll'
assembly = binary.name
tokens = ['0x06000460', '0x06000461', '0x06000462', '0x06000463', '0x06000464', '0x060007f2', '0x060007f4']
with sqlite3.connect(f'file:{database.as_posix()}?mode=ro', uri=True) as db:
    recorded_hash = db.execute('SELECT sha256 FROM assemblies WHERE file=?', (assembly,)).fetchone()[0]
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == recorded_hash
    methods = []
    for token in tokens:
        row = db.execute('SELECT token,declaring_type,name,il_sha256,body_status FROM methods WHERE assembly=? AND token=?',
                         (assembly, token)).fetchone()
        if row is None: raise ValueError('missing method ' + token)
        calls = db.execute('SELECT il_offset,opcode,target_name,target_declaring_type FROM calls '
                           'WHERE assembly=? AND caller_token=? ORDER BY il_offset', (assembly, token)).fetchall()
        methods.append({'token': row[0], 'declaring_type': row[1], 'name': row[2], 'il_sha256': row[3],
                        'body_status': row[4], 'calls': [dict(zip(('il_offset','opcode','name','type'), call)) for call in calls]})
assert [m['name'] for m in methods] == ['doCommand', 'doCommand', 'doCommandAsync', 'doCommandInt', 'doCommandIntAsync', 'MoveNext', 'MoveNext']
assert all(m['body_status'] == 'present' and m['il_sha256'] for m in methods)
summary = {'scope': 'Static REA-derived tokens and IL hashes for one distributed managed assembly; not runtime dispatch',
           'assembly_sha256': recorded_hash, 'index_sha256': hashlib.sha256(database.read_bytes()).hexdigest(),
           'methods': methods}
target = root / 'mission-planner-binary-evidence/command-method-map.json'
if target.exists(): raise FileExistsError(target)
target.write_text(json.dumps(summary, indent=2) + '\n')
print('mapped', len(methods), 'methods')
