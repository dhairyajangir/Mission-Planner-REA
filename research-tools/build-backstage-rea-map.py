"""Collect REA records for page activation and lazy page creation."""
import hashlib
import json
from pathlib import Path
import sqlite3
root = Path(__file__).resolve().parent.parent
index = root / 'mission-planner-binary-evidence/rea-supporting-index.sqlite'
assembly = root / 'mission-planner-portable/MissionPlanner.Controls.dll'
tokens = ['0x06000341', '0x06000364', '0x06000365']
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
with sqlite3.connect(f'file:{index.as_posix()}?mode=ro', uri=True) as c:
    methods = []
    for token in tokens:
        row = c.execute('select declaring_type,name,il_sha256,body_status from methods where assembly=? and token=?',
                        (assembly.name, token)).fetchone()
        assert row is not None and row[3] == 'present'
        calls = [dict(zip(('il_offset', 'opcode', 'name', 'type'), call)) for call in c.execute(
            'select il_offset,opcode,target_name,target_declaring_type from calls where assembly=? and caller_token=? order by il_offset',
            (assembly.name, token))]
        methods.append(dict(zip(('declaring_type', 'name', 'il_sha256', 'body_status'), row), token=token, calls=calls))
result = {'scope': 'REA static records; not runtime page navigation', 'assembly_sha256': sha(assembly),
          'index_sha256': sha(index), 'methods': methods}
(root / 'mission-planner-binary-evidence/backstage-page-method-map.json').write_text(json.dumps(result, indent=2) + '\n')
print('Mapped', len(methods), 'REA backstage page methods')
