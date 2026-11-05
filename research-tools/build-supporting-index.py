"""Index REA member evidence for the selected supporting assemblies."""
import json
import os
from pathlib import Path
import sqlite3

root = Path(__file__).resolve().parent.parent / 'mission-planner-binary-evidence'
source = root / os.environ.get('REA_MEMBER_SOURCE', 'assembly-members')
manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
if isinstance(manifest, dict):
    if set(manifest['requested']) != {row['file'] for row in manifest['results']}:
        raise ValueError('inventory is unfinished')
    manifest = manifest['results']
database = root / os.environ.get('REA_MEMBER_DATABASE', 'rea-supporting-index.sqlite')
if database.exists():
    raise FileExistsError(database)
db = sqlite3.connect(database)
db.executescript('''
CREATE TABLE assemblies (file TEXT PRIMARY KEY, sha256 TEXT NOT NULL);
CREATE TABLE types (assembly TEXT, token TEXT, full_name TEXT, enclosing_token TEXT,
                    PRIMARY KEY(assembly, token));
CREATE TABLE methods (assembly TEXT, token TEXT, type_token TEXT, declaring_type TEXT, name TEXT,
                      return_type TEXT, parameters_json TEXT, il_sha256 TEXT, body_status TEXT,
                      PRIMARY KEY(assembly, token));
CREATE TABLE calls (assembly TEXT, caller_token TEXT, il_offset INTEGER, opcode TEXT,
                    target_token TEXT, target_name TEXT, target_declaring_type TEXT,
                    PRIMARY KEY(assembly, caller_token, il_offset, target_token));
CREATE INDEX methods_name ON methods(name);
CREATE INDEX methods_type ON methods(declaring_type);
CREATE INDEX calls_target ON calls(target_declaring_type, target_name);
''')
for row in manifest:
    if row.get('hash_mismatch') or row['exit_code'] != 0 or row['coverage']['state'] != 'complete':
        raise ValueError(f'incomplete evidence for {row["file"]}')
    data = json.loads((source / row['evidence']).read_text(encoding='utf-8'))
    if data['subject']['digest']['sha256'] != row['sha256']:
        raise ValueError(f'hash mismatch for {row["file"]}')
    d = data['normalized_result']
    name = row['file']
    db.execute('INSERT INTO assemblies VALUES (?,?)', (name, row['sha256']))
    db.executemany('INSERT OR IGNORE INTO types VALUES (?,?,?,?)',
                   ((name, t['token'], t['full_name'], t.get('enclosing_type_token')) for t in d['types']))
    db.executemany('INSERT OR IGNORE INTO methods VALUES (?,?,?,?,?,?,?,?,?)',
                   ((name, m['token'], m['declaring_type_token'], m['declaring_type'], m['name'],
                     (m.get('signature') or {}).get('return_type'),
                     json.dumps((m.get('signature') or {}).get('parameter_types')),
                     (m.get('body') or {}).get('il_sha256'), (m.get('body') or {}).get('status'))
                    for m in d['methods']))
    db.executemany('INSERT OR IGNORE INTO calls VALUES (?,?,?,?,?,?,?)',
                   ((name, c['caller_token'], c['il_offset'], c['opcode'], c['target_token'],
                     c.get('target_name'), c.get('target_declaring_type')) for c in d['call_edges']))
    db.commit()
counts = {t: db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
          for t in ('assemblies', 'types', 'methods', 'calls')}
if counts['methods'] != sum(row['methods'] for row in manifest):
    raise ValueError(f'method count mismatch: {counts}')
print(json.dumps(counts, indent=2))
db.close()
