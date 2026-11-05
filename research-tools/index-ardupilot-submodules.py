"""Index extracted pinned submodule files after matching saved Git blob hashes."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3

root = Path(__file__).resolve().parent.parent
source = root / 'ardupilot-source/ardupilot-master'
archive = root / 'research-tools/submodule-archives'
manifest_path = root / 'ardupilot-source/extracted-submodules.json'
manifest = json.loads(manifest_path.read_text())
names = {'modules/waf':'waf', 'modules/mavlink':'mavlink', 'modules/mavlink/pymavlink':'pymavlink',
         'modules/DroneCAN/DSDL':'dsdl', 'modules/DroneCAN/dronecan_dsdlc':'dsdlc',
         'modules/DroneCAN/libcanard':'libcanard', 'modules/DroneCAN/pydronecan':'pydronecan',
         'modules/littlefs':'littlefs', 'modules/ChibiOS':'chibios', 'modules/gbenchmark':'gbenchmark',
         'modules/gsoap':'gsoap', 'modules/gtest':'gtest', 'modules/lwip':'lwip',
         'modules/Micro-CDR':'microcdr', 'modules/Micro-XRCE-DDS-Client':'microxrce',
         'modules/DroneCAN/libcanard/drivers/avr/avr-can-lib':'avrcan'}
target = root / 'integration-research/ardupilot-submodules-index.sqlite'
temporary = target.with_suffix('.sqlite.tmp')
if target.exists() or temporary.exists(): raise FileExistsError(target)
db = sqlite3.connect(temporary)
trees = {}
try:
    db.executescript('''
      CREATE TABLE files(path TEXT PRIMARY KEY, submodule TEXT, commit_sha TEXT, git_sha1 TEXT, size INTEGER, status TEXT);
      CREATE VIRTUAL TABLE source_text USING fts5(path UNINDEXED, body, tokenize='unicode61');
    ''')
    for item in manifest:
        tree_file = archive / (names[item['path']] + '-tree.json')
        data = tree_file.read_bytes()
        tree = json.loads(data)
        if tree['sha'] != item['sha'] or tree['truncated']: raise ValueError('tree mismatch')
        trees[item['path']] = hashlib.sha256(data).hexdigest()
        folder = (source / item['path']).resolve()
        io_folder = Path('\\\\?\\' + str(folder)) if os.name == 'nt' else folder
        for blob in tree['tree']:
            if blob['type'] != 'blob': continue
            path = item['path'] + '/' + blob['path']
            length = blob.get('size')
            status = 'not-indexed'
            if blob['mode'] == '120000':
                status = 'symlink-not-read'
            elif length is not None and length > 2 * 1024 * 1024:
                status = 'too-large'
            else:
                try:
                    content = (io_folder / blob['path']).read_bytes()
                    digest = hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()
                    if digest != blob['sha']:
                        status = 'worktree-differs'
                    elif b'\0' in content:
                        status = 'binary'
                    else:
                        db.execute('INSERT INTO source_text(path, body) VALUES (?, ?)', (path, content.decode('utf-8')))
                        status = 'indexed'
                except UnicodeDecodeError:
                    status = 'non-utf8'
                except OSError:
                    status = 'unreadable-or-missing'
            db.execute('INSERT INTO files VALUES (?, ?, ?, ?, ?, ?)',
                       (path, item['path'], item['sha'], blob['sha'], length, status))
        print(item['path'], 'indexed', flush=True)
    db.commit()
    counts = dict(db.execute('SELECT status, COUNT(*) FROM files GROUP BY status'))
    if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise ValueError('index integrity failure')
finally:
    db.close()
temporary.replace(target)
summary = {'scope': 'saved pinned submodule trees; indexed UTF-8 worktree files verified against Git blob hashes; '
           'symlinks, binary, changed, unreadable and >2 MiB files excluded',
           'source_manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(), 'tree_sha256': trees,
           'database_sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'status_counts': counts}
(target.parent / 'ardupilot-submodules-index-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
