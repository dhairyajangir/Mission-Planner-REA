"""Build a searchable index from REA's selected-type evidence (not a decompiler)."""
import json
from pathlib import Path
import sqlite3

root = Path(__file__).resolve().parent.parent / 'mission-planner-binary-evidence'
coverage = json.loads((root / 'rea-main-coverage.json').read_text(encoding='utf-8'))
if coverage['missing_types'] or coverage['issues']:
    raise ValueError('coverage check contains missing types or issues')
database = root / 'rea-main-index.sqlite'
if database.exists():
    raise FileExistsError(f'refusing to overwrite {database}')
db = sqlite3.connect(database)
db.executescript('''
CREATE TABLE provenance (assembly_sha256 TEXT NOT NULL, note TEXT NOT NULL);
CREATE TABLE types (token TEXT PRIMARY KEY, full_name TEXT, enclosing_token TEXT);
CREATE TABLE methods (token TEXT PRIMARY KEY, type_token TEXT, declaring_type TEXT, name TEXT,
                      return_type TEXT, parameters_json TEXT, il_sha256 TEXT, body_status TEXT);
CREATE TABLE calls (caller_token TEXT, il_offset INTEGER, opcode TEXT, target_token TEXT,
                    target_name TEXT, target_declaring_type TEXT,
                    PRIMARY KEY(caller_token, il_offset, target_token));
CREATE INDEX methods_name ON methods(name);
CREATE INDEX methods_type ON methods(declaring_type);
CREATE INDEX calls_target ON calls(target_declaring_type, target_name);
''')
db.execute('INSERT INTO provenance VALUES (?, ?)', (coverage['assembly_sha256'],
           'REA static evidence; tokens apply only to this assembly; calls are static anchors, not proven runtime execution'))
for name in ('type-batches', 'nested-type-batches'):
    folder = root / name
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    for batch in manifest['batches']:
        if batch['status'] != 'complete':
            raise ValueError(f'incomplete batch {batch["path"]}')
        d = json.loads((folder / batch['path']).read_text(encoding='utf-8'))['normalized_result']
        db.executemany('INSERT OR IGNORE INTO types VALUES (?,?,?)',
                       ((t['token'], t['full_name'], t.get('enclosing_type_token')) for t in d['types']))
        db.executemany('INSERT OR IGNORE INTO methods VALUES (?,?,?,?,?,?,?,?)',
                       ((m['token'], m['declaring_type_token'], m['declaring_type'], m['name'],
                         (m.get('signature') or {}).get('return_type'),
                         json.dumps((m.get('signature') or {}).get('parameter_types')),
                         (m.get('body') or {}).get('il_sha256'), (m.get('body') or {}).get('status'))
                        for m in d['methods']))
        db.executemany('INSERT OR IGNORE INTO calls VALUES (?,?,?,?,?,?)',
                       ((c['caller_token'], c['il_offset'], c['opcode'], c['target_token'],
                         c.get('target_name'), c.get('target_declaring_type')) for c in d['call_edges']))
    db.commit()
counts = {t: db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ('types', 'methods', 'calls')}
if counts['methods'] != coverage['unique_method_tokens']:
    raise ValueError(f'method coverage mismatch: {counts}')
print(json.dumps({'file': str(database), **counts}, indent=2))
db.close()
