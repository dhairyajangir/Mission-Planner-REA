"""Verify and extract selected pinned submodule archives into the source tree."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import zipfile

root = Path(__file__).resolve().parent.parent
source = root / 'ardupilot-source/ardupilot-master'
archive_root = root / 'research-tools/submodule-archives'
pins = {x['path']: x['sha'] for x in json.loads((root / 'ardupilot-source/archive-provenance.json').read_text())['submodule_gitlinks']}
items = [('waf', 'modules/waf'), ('mavlink', 'modules/mavlink'),
         ('pymavlink', 'modules/mavlink/pymavlink'), ('dsdl', 'modules/DroneCAN/DSDL'),
         ('dsdlc', 'modules/DroneCAN/dronecan_dsdlc'), ('libcanard', 'modules/DroneCAN/libcanard'),
         ('pydronecan', 'modules/DroneCAN/pydronecan'), ('chibios', 'modules/ChibiOS'),
         ('gbenchmark', 'modules/gbenchmark'), ('gsoap', 'modules/gsoap'), ('gtest', 'modules/gtest'),
         ('littlefs', 'modules/littlefs'), ('lwip', 'modules/lwip'),
         ('microcdr', 'modules/Micro-CDR'), ('microxrce', 'modules/Micro-XRCE-DDS-Client'),
         ('avrcan', 'modules/DroneCAN/libcanard/drivers/avr/avr-can-lib')]
manifest_path = root / 'ardupilot-source/extracted-submodules.json'
result = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else []
if any(name == 'pymavlink' for name, _ in items):
    mavtree = json.loads((archive_root / 'mavlink-tree.json').read_text(encoding='utf-8'))
    if mavtree['sha'] != pins['modules/mavlink'] or mavtree['truncated']:
        raise ValueError('unverified parent MAVLink tree')
    pins['modules/mavlink/pymavlink'] = next(x['sha'] for x in mavtree['tree']
                                              if x['path'] == 'pymavlink' and x['type'] == 'commit')
if any(name == 'avrcan' for name, _ in items):
    cantree = json.loads((archive_root / 'libcanard-tree.json').read_text(encoding='utf-8'))
    if cantree['sha'] != pins['modules/DroneCAN/libcanard'] or cantree['truncated']:
        raise ValueError('unverified parent libcanard tree')
    pins['modules/DroneCAN/libcanard/drivers/avr/avr-can-lib'] = next(
        x['sha'] for x in cantree['tree'] if x['path'] == 'drivers/avr/avr-can-lib' and x['type'] == 'commit')
resume = '--resume' in sys.argv[1:]
requested = {x for x in sys.argv[1:] if x != '--resume'}
if requested:
    items = [item for item in items if item[0] in requested]
    if len(items) != len(requested):
        raise ValueError('unknown or duplicate requested module name')
for name, path in items:
    target = (source / path).resolve()
    if not target.is_relative_to(source.resolve()):
        raise ValueError(f'bad target {target}')
    io_target = Path('\\\\?\\' + str(target)) if os.name == 'nt' else target
    tree = json.loads((archive_root / f'{name}-tree.json').read_text(encoding='utf-8'))
    expected = pins[path]
    if tree['sha'] != expected or tree['truncated']:
        raise ValueError(f'bad tree for {path}')
    blobs = {x['path']: x['sha'] for x in tree['tree'] if x['type'] == 'blob'}
    zip_path = archive_root / f'{name}.zip'
    with zipfile.ZipFile(zip_path) as z:
        if z.comment.decode('ascii') != expected:
            raise ValueError(f'bad ZIP comment for {path}')
        roots = {e.filename.split('/')[0] for e in z.infolist()}
        if len(roots) != 1:
            raise ValueError(f'unexpected ZIP roots for {path}')
        prefix = next(iter(roots)) + '/'
        found = {}
        symlink_entries = []
        for entry in z.infolist():
            if entry.is_dir():
                continue
            rel = entry.filename.removeprefix(prefix)
            if rel == entry.filename or not (target / rel).resolve().is_relative_to(target):
                raise ValueError(f'unsafe path {entry.filename}')
            if rel in found:
                raise ValueError(f'duplicate path {rel}')
            if stat.S_ISLNK(entry.external_attr >> 16):
                symlink_entries.append(rel)
            h = hashlib.sha1(f'blob {entry.file_size}\0'.encode())
            with z.open(entry) as f:
                while chunk := f.read(1024 * 1024):
                    h.update(chunk)
            found[rel] = h.hexdigest()
        supplement = archive_root / f'{name}-export-ignored'
        supplemental_files = []
        if supplement.exists():
            for f in supplement.rglob('*'):
                if not f.is_file():
                    continue
                rel = f.relative_to(supplement).as_posix()
                if rel in found or not (target / rel).resolve().is_relative_to(target):
                    raise ValueError(f'duplicate or unsafe supplemental path {rel}')
                data = f.read_bytes()
                found[rel] = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
                supplemental_files.append((f, rel))
        if found != blobs:
            raise ValueError(f'blob mismatch for {path}: found {len(found)}, expected {len(blobs)}')
        existing = [p for p in io_target.rglob('*') if p.is_file()] if io_target.exists() else []
        if existing and not resume:
            raise FileExistsError(f'refusing to overwrite {len(existing)} files under {target}')
        for p in existing:
            rel = p.relative_to(io_target).as_posix()
            data = p.read_bytes()
            digest = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
            if rel not in found or digest != found[rel]:
                raise ValueError(f'existing file differs from pinned source: {p}')
        for entry in z.infolist():
            if entry.is_dir():
                continue
            rel = entry.filename[len(prefix):]
            dest = io_target / rel
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(entry) as src, dest.open('wb') as dst:
                shutil.copyfileobj(src, dst)
        for src, rel in supplemental_files:
            dest = io_target / rel
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
        result = [item for item in result if item['path'] != path]
        result.append({'path': path, 'sha': expected, 'matched_blobs': len(found),
                       'nested_gitlinks': [x for x in tree['tree'] if x['type'] == 'commit'],
                       'symlink_entries_stored_as_files': symlink_entries})
        print(f'{path}: verified and extracted {len(found)} blobs')
        manifest_path.write_text(json.dumps(result, indent=2) + '\n')
