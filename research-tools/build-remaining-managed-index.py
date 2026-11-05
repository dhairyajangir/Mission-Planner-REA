"""Create a snapshot index of complete REA member results only.

The summary explicitly lists missing and partial assemblies. This index cannot
stand in for missing member evidence or establish runtime call behavior.
"""
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3

root = Path(__file__).resolve().parent.parent
evidence = root / 'mission-planner-binary-evidence'
source = evidence / 'remaining-managed-members'
manifest_file = source / 'manifest.json'
manifest_bytes = manifest_file.read_bytes()
manifest = json.loads(manifest_bytes)
available = [r for r in manifest['results'] if r.get('exit_code') == 0 and r.get('subject_matches') and
             (r.get('coverage') or {}).get('state') == 'complete']
recorded = {r['path'] for r in manifest['results']}
partial = [r['path'] for r in manifest['results'] if r not in available]
missing = [p for p in manifest['requested_paths'] if p not in recorded]
target = evidence / 'rea-remaining-index.sqlite'
temporary = target.with_suffix('.sqlite.tmp')
if temporary.exists():
    raise FileExistsError('unfinished temporary index exists: ' + str(temporary))
db = sqlite3.connect(temporary)
try:
    db.executescript('''
      CREATE TABLE assemblies (file TEXT PRIMARY KEY, sha256 TEXT NOT NULL, evidence TEXT NOT NULL);
      CREATE TABLE types (assembly TEXT, token TEXT, full_name TEXT, enclosing_token TEXT, PRIMARY KEY(assembly, token));
      CREATE TABLE methods (assembly TEXT, token TEXT, type_token TEXT, declaring_type TEXT, name TEXT,
                            return_type TEXT, parameters_json TEXT, il_sha256 TEXT, body_status TEXT,
                            PRIMARY KEY(assembly, token));
      CREATE TABLE calls (assembly TEXT, caller_token TEXT, il_offset INTEGER, opcode TEXT, target_token TEXT,
                          target_name TEXT, target_declaring_type TEXT, PRIMARY KEY(assembly, caller_token, il_offset, target_token));
      CREATE INDEX methods_name ON methods(name);
      CREATE INDEX methods_type ON methods(declaring_type);
      CREATE INDEX calls_target ON calls(target_declaring_type, target_name);
    ''')
    for row in available:
        with gzip.open(source / row['evidence'], 'rt', encoding='utf-8') as stream:
            data = json.load(stream)
        n = data['normalized_result']
        if data['subject']['digest']['sha256'] != row['sha256'] or n['coverage']['state'] != 'complete':
            raise ValueError('evidence mismatch: ' + row['path'])
        name = row['path']
        db.execute('INSERT INTO assemblies VALUES (?,?,?)', (name, row['sha256'], row['evidence']))
        db.executemany('INSERT OR IGNORE INTO types VALUES (?,?,?,?)',
                       ((name, t['token'], t['full_name'], t.get('enclosing_type_token')) for t in n['types']))
        db.executemany('INSERT OR IGNORE INTO methods VALUES (?,?,?,?,?,?,?,?,?)',
                       ((name, m['token'], m['declaring_type_token'], m['declaring_type'], m['name'],
                         (m.get('signature') or {}).get('return_type'), json.dumps((m.get('signature') or {}).get('parameter_types')),
                         (m.get('body') or {}).get('il_sha256'), (m.get('body') or {}).get('status')) for m in n['methods']))
        db.executemany('INSERT OR IGNORE INTO calls VALUES (?,?,?,?,?,?,?)',
                       ((name, c['caller_token'], c['il_offset'], c['opcode'], c['target_token'],
                         c.get('target_name'), c.get('target_declaring_type')) for c in n['call_edges']))
        db.commit()
    counts = {table: db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
              for table in ('assemblies', 'types', 'methods', 'calls')}
    if counts['methods'] != sum(row['methods'] for row in available):
        raise ValueError('method count mismatch')
    integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
    if integrity != 'ok':
        raise ValueError('SQLite integrity check failed')
finally:
    db.close()
temporary.replace(target)
summary = {'scope': 'complete individual REA member results only; not runtime behavior',
           'source_manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
           'database_sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'counts': counts,
           'requested': len(manifest['requested_paths']), 'partial': partial, 'not_yet_processed': missing}
(evidence / 'rea-remaining-index-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps({'counts': counts, 'partial': len(partial), 'not_yet_processed': len(missing)}, indent=2))
