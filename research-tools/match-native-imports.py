"""Compare static DLL and export names; does not model the Windows loader."""
import hashlib
import json
from pathlib import Path
import sqlite3

root = Path(__file__).resolve().parent.parent
base = root / 'mission-planner-binary-evidence'
boundary_db = base / 'managed-native-all/index.sqlite'
native_manifest = base / 'native-exports/manifest.json'
manifest = json.loads(native_manifest.read_text())
def canonical(name):
    value = name.replace('\\', '/').split('/')[-1].lower()
    return value if value.endswith('.dll') else value + '.dll'

exports = {}
for item in manifest['results']:
    data = json.loads((native_manifest.parent / item['evidence']).read_text())
    if data['subject']['digest']['sha256'] != item['sha256']: raise ValueError('native digest mismatch')
    n = data['normalized_result']
    if n['coverage']['status'] != 'complete': continue
    exports.setdefault(canonical(item['path']), []).append({
        'path': item['path'], 'sha256': item['sha256'], 'architecture': n['architecture'],
        'names': {x['name'] for x in n['exports'] if x['name'] is not None}})

target = base / 'managed-native-all/native-name-matches.sqlite'
temporary = target.with_suffix('.sqlite.tmp')
if target.exists() or temporary.exists(): raise FileExistsError(target)
with sqlite3.connect(f'file:{boundary_db.as_posix()}?mode=ro', uri=True) as source:
    imports = source.execute('SELECT path, member_token, scope, import_name FROM imports').fetchall()
db = sqlite3.connect(temporary)
try:
    db.execute('CREATE TABLE matches(assembly TEXT, member_token TEXT, scope TEXT, import_name TEXT, '
               'native_path TEXT, native_sha256 TEXT, architecture TEXT, exact_export INTEGER)')
    for assembly, token, scope, name in imports:
        if not scope: continue
        for item in exports.get(canonical(scope), []):
            db.execute('INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (assembly, token, scope, name,
                item['path'], item['sha256'], str(item['architecture']), int(name in item['names'])))
    db.commit()
    count = db.execute('SELECT COUNT(*) FROM matches').fetchone()[0]
    exact = db.execute('SELECT COUNT(*) FROM matches WHERE exact_export=1').fetchone()[0]
    if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise ValueError('database integrity')
finally:
    db.close()
temporary.replace(target)
summary = {'scope': 'case-insensitive DLL basename candidate plus exact export-name comparison; not loader resolution',
           'boundary_index_sha256': hashlib.sha256(boundary_db.read_bytes()).hexdigest(),
           'native_manifest_sha256': hashlib.sha256(native_manifest.read_bytes()).hexdigest(),
           'database_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
           'candidate_rows': count, 'exact_name_rows': exact}
(target.parent / 'native-name-matches-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
