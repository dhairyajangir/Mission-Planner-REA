"""Index unchanged UTF-8 source files from the verified ArduPilot Git tree."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
project = sys.argv[1] if len(sys.argv) > 1 else 'ardupilot'
if project == 'ardupilot':
    source = root / 'ardupilot-source/ardupilot-master'
    commit = '72b238201f5ea3b556e3809b2ec704fcf701474a'
elif project in ('mission-planner', 'mission-planner-normalized'):
    source = root / 'mission-planner-1.3.83-source'
    commit = 'b78a7495fec69793f2fcc13be4b6a3d9e06b3e4e'
else:
    raise ValueError('expected ardupilot or mission-planner')
head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD']).decode().strip()
if head != commit: raise ValueError('source checkout HEAD changed')
env = dict(os.environ, GIT_NO_LAZY_FETCH='1')
tree = subprocess.check_output(['git', '-C', str(source), 'ls-tree', '-r', '-z', commit], env=env)
target = root / ('integration-research/' + project + '-source-index.sqlite')
temporary = target.with_suffix('.sqlite.tmp')
if target.exists() or temporary.exists(): raise FileExistsError(target)
db = sqlite3.connect(temporary)
try:
    db.executescript('''
      CREATE TABLE files(path TEXT PRIMARY KEY, mode TEXT, object_type TEXT, git_sha1 TEXT, size INTEGER, status TEXT);
      CREATE VIRTUAL TABLE source_text USING fts5(path UNINDEXED, body, tokenize='unicode61');
    ''')
    for item in tree.split(b'\0'):
        if not item: continue
        metadata, pathbytes = item.split(b'\t', 1)
        mode, kind, digest = metadata.decode('ascii').split()
        path = pathbytes.decode('utf-8')
        length = None
        status = 'not-indexed'
        if kind == 'commit':
            status = 'submodule-gitlink'
        elif mode == '120000':
            status = 'symlink-not-read'
        else:
            try:
                length = (source / path).stat().st_size
                if length > 2 * 1024 * 1024:
                    db.execute('INSERT INTO files VALUES (?, ?, ?, ?, ?, ?)', (path, mode, kind, digest, length, 'too-large'))
                    continue
                content = (source / path).read_bytes()
                digest_actual = hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()
                if digest_actual != digest:
                    normalized = content.replace(b'\r\n', b'\n')
                    normalized_sha = hashlib.sha1(b'blob ' + str(len(normalized)).encode() + b'\0' + normalized).hexdigest()
                    if project == 'mission-planner-normalized' and normalized_sha == digest and b'\0' not in normalized:
                        db.execute('INSERT INTO source_text(path, body) VALUES (?, ?)', (path, normalized.decode('utf-8')))
                        status = 'indexed-crlf-normalized'
                    else:
                        status = 'worktree-differs'
                elif b'\0' in content:
                    status = 'binary'
                else:
                    text = content.decode('utf-8')
                    db.execute('INSERT INTO source_text(path, body) VALUES (?, ?)', (path, text))
                    status = 'indexed'
            except UnicodeDecodeError:
                status = 'non-utf8'
            except OSError:
                status = 'unreadable-or-missing'
        db.execute('INSERT INTO files VALUES (?, ?, ?, ?, ?, ?)', (path, mode, kind, digest, length, status))
    db.commit()
    counts = dict(db.execute('SELECT status, COUNT(*) FROM files GROUP BY status'))
    if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise ValueError('index integrity failure')
finally:
    db.close()
temporary.replace(target)
summary = {'commit': commit, 'scope': 'tracked main-repository tree; indexed UTF-8 bytes matched Git blobs, with optional '
           'CRLF to LF normalization recorded separately; submodules, symlinks, binary, changed, unreadable and >2 MiB files excluded',
           'tree_sha256': hashlib.sha256(tree).hexdigest(), 'database_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
           'status_counts': counts}
(target.parent / (project + '-source-index-summary.json')).write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
