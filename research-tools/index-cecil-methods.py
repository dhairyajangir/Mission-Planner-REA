"""Index a Cecil metadata capture and compare method totals with its type inventory."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

root = Path(__file__).resolve().parent.parent
name = sys.argv[1]
if Path(name).name != name or name in ('.', '..'):
    raise ValueError('expected a root-level assembly filename')
slug = Path(name).stem.lower().replace('.', '-')
base = root / 'mission-planner-binary-evidence/remaining-managed-members'
binary = root / 'mission-planner-portable' / name
digest = hashlib.sha256(binary.read_bytes()).hexdigest()
entry = next(row for row in json.loads((base / 'manifest.json').read_text())['results'] if row['path'] == name)
if digest != entry['sha256']:
    raise ValueError('assembly hash changed')
type_file = base / (slug + '-cecil-types.tsv')
capture = base / (slug + '-cecil-methods.tsv.gz')
expected = {row[0]: int(row[4]) for row in (line.split('\t') for line in type_file.read_text().splitlines())}
target = base / (slug + '-cecil-index.sqlite')
temporary = target.with_suffix('.sqlite.tmp')
if target.exists() or temporary.exists():
    raise FileExistsError(target)
decode = lambda value: base64.b64decode(value, validate=True).decode('utf-8')
db = sqlite3.connect(temporary)
try:
    db.executescript('''CREATE TABLE methods(token TEXT PRIMARY KEY, type_token TEXT, signature TEXT, has_body INTEGER, instruction_count INTEGER);
      CREATE TABLE method_references(caller_token TEXT, il_offset INTEGER, opcode TEXT, target_signature TEXT,
                                     PRIMARY KEY(caller_token, il_offset));
      CREATE INDEX ref_target ON method_references(target_signature);''')
    with gzip.open(capture, 'rt', encoding='utf-8') as stream:
        for line in stream:
            row = line.rstrip('\n').split('\t')
            if row[0] == 'M' and len(row) == 6:
                db.execute('INSERT INTO methods VALUES (?,?,?,?,?)', (row[1], row[2], decode(row[3]), int(row[4]), int(row[5])))
            elif row[0] == 'C' and len(row) == 5:
                db.execute('INSERT INTO method_references VALUES (?,?,?,?)', (row[1], int(row[2]), decode(row[3]), decode(row[4])))
            else:
                raise ValueError('invalid capture row')
    db.commit()
    actual = dict(db.execute('SELECT type_token, COUNT(*) FROM methods GROUP BY type_token'))
    if any(actual.get(token, 0) != count for token, count in expected.items()) or set(actual) - set(expected):
        raise ValueError('type method counts differ from Cecil type inventory')
    if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('SQLite integrity failed')
    counts = {table: db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] for table in ('methods', 'method_references')}
finally:
    db.close()
temporary.replace(target)
summary = {'assembly_sha256': digest, 'type_inventory_sha256': hashlib.sha256(type_file.read_bytes()).hexdigest(),
           'capture_sha256': hashlib.sha256(capture.read_bytes()).hexdigest(),
           'database_sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'counts': counts,
           'scope': 'Cecil static method definitions and method-reference IL instructions; not REA and not runtime execution'}
(base / (slug + '-cecil-index-summary.json')).write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
