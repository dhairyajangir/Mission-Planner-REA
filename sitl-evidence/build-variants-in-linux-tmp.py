"""Build the verified archive in a temporary Linux directory and retain evidence.

The workspace is on a slow Windows/WSL mount. This copies the original archive
and pinned submodule archives to /tmp, extracts them there, and writes all build
logs and the resulting binary back into the workspace. No source ZIP is changed.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import traceback
import zipfile

evidence = Path(__file__).resolve().parent
project = evidence.parent
source_zip = Path('/mnt/c/Users/think/OneDrive/Desktop/Projects/drone/ardupilot-master.zip')
expected_zip_sha256 = '7edc50142718c3c98c1c679cf398ce7e258e29ec889ae65a53855b7a2bce931d'
expected_commit = '72b238201f5ea3b556e3809b2ec704fcf701474a'
archive_dir = project / 'research-tools/submodule-archives'
manifest = json.loads((project / 'ardupilot-source/extracted-submodules.json').read_text())
names = {'modules/waf':'waf', 'modules/mavlink':'mavlink', 'modules/mavlink/pymavlink':'pymavlink',
         'modules/DroneCAN/DSDL':'dsdl', 'modules/DroneCAN/dronecan_dsdlc':'dsdlc',
         'modules/DroneCAN/libcanard':'libcanard', 'modules/DroneCAN/pydronecan':'pydronecan',
         'modules/littlefs':'littlefs', 'modules/ChibiOS':'chibios', 'modules/gbenchmark':'gbenchmark',
         'modules/gsoap':'gsoap', 'modules/gtest':'gtest', 'modules/lwip':'lwip',
         'modules/Micro-CDR':'microcdr', 'modules/Micro-XRCE-DDS-Client':'microxrce',
         'modules/DroneCAN/libcanard/drivers/avr/avr-can-lib':'avrcan'}
if not set(names).issubset({x['path'] for x in manifest}):
    raise ValueError('not all required pinned submodule archives were verified')
work = Path(tempfile.mkdtemp(prefix='ardupilot-sitl-72b23820-', dir='/tmp'))
result = {'temp_directory': str(work), 'commit': expected_commit, 'status': 'starting', 'steps': [],
          'limitations': ['Temporary source tree uses verified archives and copied Git metadata; it is not a pristine recursive Git checkout.',
                          'Compiler output is a local build, not an official release.']}
result_file = evidence / 'archive-linux-variants-build-status.json'

def save(step, status, **extra):
    result['steps'].append({'step': step, 'status': status, **extra})
    result['status'] = ('failed' if status == 'failed' else
                        'complete' if step == 'publish all local SITL binaries' and status == 'complete' else 'running')
    result_file.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f'{step}: {status}', flush=True)

def unpack(archive, dest, expected_comment):
    dest = dest.resolve()
    with zipfile.ZipFile(archive) as z:
        if z.comment.decode('ascii') != expected_comment:
            raise ValueError(f'archive comment mismatch: {archive}')
        roots = {x.filename.split('/')[0] for x in z.infolist()}
        if len(roots) != 1:
            raise ValueError(f'bad ZIP root: {archive}')
        prefix = next(iter(roots)) + '/'
        for entry in z.infolist():
            if entry.is_dir():
                continue
            relative = entry.filename.removeprefix(prefix)
            target = (dest / relative).resolve()
            if relative == entry.filename or not target.is_relative_to(dest):
                raise ValueError(f'unsafe archive entry: {entry.filename}')
            target.parent.mkdir(parents=True, exist_ok=True)
            if stat.S_ISLNK(entry.external_attr >> 16):
                link = z.read(entry).decode('utf-8')
                if Path(link).is_absolute() or not (target.parent / link).resolve().is_relative_to(dest):
                    raise ValueError(f'unsafe symlink: {entry.filename}')
                target.symlink_to(link)
                continue
            with z.open(entry) as src, target.open('wb') as dst:
                shutil.copyfileobj(src, dst)
            mode = entry.external_attr >> 16
            if mode & 0o111:
                target.chmod(target.stat().st_mode | 0o111)

try:
    save('create temporary workspace', 'running')
    local_zip = work / 'source.zip'
    digest = hashlib.sha256()
    with source_zip.open('rb') as src, local_zip.open('wb') as dst:
        while chunk := src.read(4 * 1024 * 1024):
            digest.update(chunk)
            dst.write(chunk)
    if digest.hexdigest() != expected_zip_sha256:
        raise ValueError('source ZIP SHA-256 mismatch')
    save('copy verified source ZIP', 'complete', sha256=digest.hexdigest())
    source = work / 'source'
    unpack(local_zip, source, expected_commit)
    save('extract source ZIP', 'complete')
    for item in manifest:
        if item['path'] not in names:
            continue
        archive = archive_dir / (names[item['path']] + '.zip')
        unpack(archive, source / item['path'], item['sha'])
        if item['path'] == 'modules/lwip':
            supplement = archive_dir / 'lwip-export-ignored'
            shutil.copytree(supplement, source / item['path'], dirs_exist_ok=True)
    save('extract verified pinned dependencies', 'complete', count=len(names))
    shutil.copytree(project / 'ardupilot-source/ardupilot-master/.git', source / '.git')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    if head != expected_commit:
        raise ValueError('copied Git HEAD mismatch')
    save('verify copied Git revision metadata', 'complete', head=head)
    # Avoid thousands of slow Python module reads through /mnt/c during build.
    deps = work / 'python'
    shutil.copytree(evidence / 'python', deps)
    env = os.environ.copy()
    env['PYTHONPATH'] = str(deps)
    for step, args, filename in (
        ('configure', ['python3', 'waf', 'configure', '--board', 'sitl', '--no-submodule-update'], 'archive-linux-variants-configure.log'),
        *[(f'build {name}', ['python3', 'waf', name, '-j', '2'], f'archive-linux-{name}-build.log') for name in ('plane', 'rover', 'sub')]):
        save(step, 'running')
        with (evidence / filename).open('wb') as log:
            p = subprocess.run(args, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=3600)
        if p.returncode:
            raise RuntimeError(f'{step} failed with exit {p.returncode}; see {filename}')
        save(step, 'complete', log=filename)
        if step.startswith('build '):
            name = step.split()[1]
            binary = source / 'build/sitl/bin' / ('ardu' + name)
            output = evidence / 'archive-built-variants'
            output.mkdir(exist_ok=True)
            dest = output / binary.name
            if dest.exists():
                raise FileExistsError(f'refusing to overwrite {dest}')
            shutil.copy2(binary, dest)
            digest = hashlib.sha256(binary.read_bytes()).hexdigest()
            if hashlib.sha256(dest.read_bytes()).hexdigest() != digest:
                raise ValueError('copied binary SHA-256 mismatch')
            save(f'publish {name} binary', 'complete', path=str(dest), sha256=digest)
    save('publish all local SITL binaries', 'complete')
except Exception:
    result['error'] = traceback.format_exc()
    save('build workflow', 'failed')
    raise
