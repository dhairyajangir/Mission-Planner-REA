"""Index saved REA native-boundary captures; preserve incomplete rows as such."""
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3

root = Path(__file__).resolve().parent.parent
base = root / 'mission-planner-binary-evidence/managed-native-all'
manifest_file = base / 'manifest.json'
manifest = json.loads(manifest_file.read_text())
if len(manifest['results']) != manifest['requested']: raise ValueError('scan still incomplete')
target = base / 'index.sqlite'
temporary = base / 'index.sqlite.tmp'
if target.exists() or temporary.exists(): raise FileExistsError(target)
db = sqlite3.connect(temporary)
try:
    db.executescript('''
      CREATE TABLE assemblies(path TEXT PRIMARY KEY, sha256 TEXT NOT NULL, coverage TEXT, error TEXT);
      CREATE TABLE imports(path TEXT, member_token TEXT, member_name TEXT, scope TEXT, import_name TEXT,
                           call_convention TEXT, charset TEXT, flags INTEGER);
      CREATE TABLE native_implementations(path TEXT, token TEXT, name TEXT, code_type TEXT,
                                          managed_kind TEXT, boundary_kind TEXT, body_interpretation TEXT);
      CREATE INDEX imports_scope ON imports(scope, import_name);
    ''')
    for row in manifest['results']:
        path = row['path']
        coverage = row.get('coverage', {}).get('state') if row.get('exit_code') == 0 else None
        error = row.get('error') or (('exit code ' + str(row['exit_code'])) if row.get('exit_code') not in (None, 0) else None)
        db.execute('INSERT INTO assemblies VALUES (?, ?, ?, ?)', (path, row['sha256'], coverage, error))
        if 'evidence' not in row: continue
        capture = base / row['evidence']
        if hashlib.sha256(capture.read_bytes()).hexdigest() != row['evidence_sha256']: raise ValueError('capture hash')
        with gzip.open(capture, 'rt', encoding='utf-8') as f: data = json.load(f)
        if data['subject']['digest']['sha256'] != row['sha256']: raise ValueError('subject digest')
        n = data['normalized_result']
        if n['coverage'] != row['coverage']: raise ValueError('coverage mismatch')
        for p in n['pinvoke_imports']:
            db.execute('INSERT INTO imports VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (path, p['member_token'], p['member_name'],
                p['import_scope_name'], p['import_name'], p['call_convention'], p['char_set'], p['mapping_flags']))
        for item in n['native_implementations']:
            db.execute('INSERT INTO native_implementations VALUES (?, ?, ?, ?, ?, ?, ?)', (path, item['token'],
                item['name'], item['code_type'], item['managed_kind'], item['boundary_kind'], item['body_interpretation']))
    db.commit()
    counts = {name: db.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0]
              for name in ('assemblies', 'imports', 'native_implementations')}
    by_coverage = dict(db.execute('SELECT COALESCE(coverage, "error"), COUNT(*) FROM assemblies GROUP BY coverage'))
    if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise ValueError('database integrity')
finally:
    db.close()
temporary.replace(target)
summary = {'scope': 'static managed declarations only; not proof of native resolution or execution',
           'manifest_sha256': hashlib.sha256(manifest_file.read_bytes()).hexdigest(),
           'database_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
           'counts': counts, 'coverage': by_coverage}
(base / 'index-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
