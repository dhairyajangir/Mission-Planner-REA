"""Collect selected REA records for typed and legacy fence paths."""
import hashlib
import json
from pathlib import Path
import sqlite3
root = Path(__file__).resolve().parent.parent
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
groups = [
    ('mission-planner-binary-evidence/rea-supporting-index.sqlite', 'mission-planner-portable/MissionPlanner.ArduPilot.dll',
     ['0x06000475', '0x0600047d', '0x06000482', '0x06000483', '0x06000484', '0x060004a0', '0x060004a9']),
    ('mission-planner-binary-evidence/rea-main-index.sqlite', 'mission-planner-portable/MissionPlanner.exe',
     ['0x06000b91', '0x06000bd4', '0x06000bd5', '0x06000bde', '0x06000bdf'])]
result = {'scope': 'REA static identities and call references; no UI execution claim', 'groups': []}
for index_path, assembly_path, tokens in groups:
    index = root / index_path; assembly = root / assembly_path
    methods = []
    with sqlite3.connect(f'file:{index.as_posix()}?mode=ro', uri=True) as c:
        for token in tokens:
            if assembly.name == 'MissionPlanner.exe':
                row = c.execute('select declaring_type,name,il_sha256,body_status from methods where token=?', (token,)).fetchone()
                calls = c.execute('select il_offset,opcode,target_name,target_declaring_type from calls where caller_token=? order by il_offset', (token,))
            else:
                row = c.execute('select declaring_type,name,il_sha256,body_status from methods where assembly=? and token=?', (assembly.name, token)).fetchone()
                calls = c.execute('select il_offset,opcode,target_name,target_declaring_type from calls where assembly=? and caller_token=? order by il_offset', (assembly.name, token))
            assert row is not None and row[3] == 'present'
            methods.append(dict(zip(('declaring_type', 'name', 'il_sha256', 'body_status'), row), token=token,
                                calls=[dict(zip(('il_offset', 'opcode', 'name', 'type'), call)) for call in calls]))
    result['groups'].append({'index_path': index_path, 'assembly_path': assembly_path, 'index_sha256': sha(index),
                             'assembly_sha256': sha(assembly), 'methods': methods})
(root / 'mission-planner-binary-evidence/fence-method-map.json').write_text(json.dumps(result, indent=2) + '\n')
print('Mapped', sum(len(g['methods']) for g in result['groups']), 'REA methods')
