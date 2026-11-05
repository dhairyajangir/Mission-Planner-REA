"""Collect REA terrain responder records from the distributed utility assembly."""
import hashlib
import json
from pathlib import Path
import sqlite3
root = Path(__file__).resolve().parent.parent
index = root / 'mission-planner-binary-evidence/rea-supporting-index.sqlite'
assembly = root / 'mission-planner-portable/MissionPlanner.Utilities.dll'
tokens = ['0x06000715', '0x06000718', '0x06000719', '0x0600071a', '0x0600071b']
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
with sqlite3.connect(f'file:{index.as_posix()}?mode=ro', uri=True) as c:
    methods = []
    for token in tokens:
        row = c.execute('select declaring_type,name,il_sha256,body_status from methods where assembly=? and token=?',
                        (assembly.name, token)).fetchone()
        assert row is not None and row[0].endswith('TerrainFollow') and row[3] == 'present'
        calls = [dict(zip(('il_offset', 'opcode', 'name', 'type'), call)) for call in c.execute(
            'select il_offset,opcode,target_name,target_declaring_type from calls where assembly=? and caller_token=? order by il_offset',
            (assembly.name, token))]
        methods.append(dict(zip(('declaring_type', 'name', 'il_sha256', 'body_status'), row), token=token, calls=calls))
result = {'scope': 'REA static records for distributed Utilities; runtime terrain test uses patched Utilities',
          'assembly_sha256': sha(assembly), 'index_sha256': sha(index), 'methods': methods}
(root / 'mission-planner-binary-evidence/terrain-method-map.json').write_text(json.dumps(result, indent=2) + '\n')
print('Mapped', len(methods), 'REA terrain methods')
