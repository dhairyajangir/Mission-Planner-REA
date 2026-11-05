"""Index REA batches with explicit, independently checked coverage."""
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

root = Path(__file__).resolve().parent.parent
relative = sys.argv[1] if len(sys.argv) > 1 else 'Accord.Statistics.dll'
allow_partial = '--allow-partial' in sys.argv[2:]
if Path(relative).name != relative or relative in ('.', '..'):
    raise ValueError('expected a root-level assembly filename')
slug = Path(relative).stem.lower().replace('.', '-')
base = root / 'mission-planner-binary-evidence' / (slug + ('-mixed-batches' if '--mixed' in sys.argv[2:] else '-batches'))
summary = json.loads((base / 'coverage-summary.json').read_text())
manifest = json.loads((base / 'manifest.json').read_text())
if (not summary['complete'] and not allow_partial) or summary['assembly_sha256'] != manifest['assembly_sha256']:
    raise ValueError('independent coverage comparison is incomplete or for another assembly')
if summary['errors'] or summary['unexpected_types']:
    raise ValueError('coverage comparison contains errors or unexpected types')
stem = 'index' if summary['complete'] else 'index-partial'
target = base / (stem + '.sqlite')
temp = base / (stem + '.sqlite.tmp')
if temp.exists():
    raise FileExistsError(temp)
db = sqlite3.connect(temp)
try:
    db.executescript('''
        CREATE TABLE types (token TEXT PRIMARY KEY, full_name TEXT, enclosing_token TEXT);
        CREATE TABLE methods (token TEXT PRIMARY KEY, type_token TEXT, declaring_type TEXT, name TEXT,
                              return_type TEXT, parameters_json TEXT, il_sha256 TEXT, body_status TEXT);
        CREATE TABLE calls (caller_token TEXT, il_offset INTEGER, opcode TEXT, target_token TEXT,
                            target_name TEXT, target_declaring_type TEXT,
                            PRIMARY KEY(caller_token, il_offset, target_token));
        CREATE INDEX methods_name ON methods(name);
        CREATE INDEX calls_target ON calls(target_declaring_type, target_name);
    ''')
    for batch in manifest['batches']:
        if batch['status'] != 'complete':
            if allow_partial:
                continue
            raise ValueError('partial batch in manifest')
        with gzip.open(base / batch['evidence'], 'rt', encoding='utf-8') as stream:
            data = json.load(stream)
        if data['subject']['digest']['sha256'] != summary['assembly_sha256']:
            raise ValueError('batch subject mismatch')
        n = data['normalized_result']
        if n['coverage']['state'] != 'complete':
            raise ValueError('batch coverage mismatch')
        db.executemany('INSERT OR IGNORE INTO types VALUES (?,?,?)',
                       ((t['token'], t['full_name'], t.get('enclosing_type_token')) for t in n['types']))
        db.executemany('INSERT OR IGNORE INTO methods VALUES (?,?,?,?,?,?,?,?)',
                       ((m['token'], m['declaring_type_token'], m['declaring_type'], m['name'],
                         (m.get('signature') or {}).get('return_type'),
                         json.dumps((m.get('signature') or {}).get('parameter_types')),
                         (m.get('body') or {}).get('il_sha256'), (m.get('body') or {}).get('status'))
                        for m in n['methods']))
        db.executemany('INSERT OR IGNORE INTO calls VALUES (?,?,?,?,?,?)',
                       ((c['caller_token'], c['il_offset'], c['opcode'], c['target_token'],
                         c.get('target_name'), c.get('target_declaring_type')) for c in n['call_edges']))
        db.commit()
    counts = {table: db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
              for table in ('types', 'methods', 'calls')}
    if counts['types'] != summary['observed_types'] or counts['methods'] != summary['observed_methods']:
        raise ValueError('index counts differ from the REA coverage comparison')
    if summary['complete'] and (counts['types'] != summary['expected_types'] or counts['methods'] != summary['expected_methods']):
        raise ValueError('index counts differ from independently enumerated metadata')
    if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('SQLite integrity check failed')
finally:
    db.close()
temp.replace(target)
result = {'assembly_sha256': summary['assembly_sha256'], 'database_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
          'coverage_summary_sha256': hashlib.sha256((base / 'coverage-summary.json').read_bytes()).hexdigest(),
          'manifest_sha256': hashlib.sha256((base / 'manifest.json').read_bytes()).hexdigest(), 'counts': counts,
          'complete': summary['complete'], 'expected_types': summary['expected_types'], 'expected_methods': summary['expected_methods'],
          'scope': 'static REA batch results; no runtime execution claim'}
(base / (stem + '-summary.json')).write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
