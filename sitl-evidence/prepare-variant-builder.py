from pathlib import Path

source = Path(__file__).with_name('build-exact-in-linux-tmp.py').read_text()
source = source.replace('archive-linux-build-status.json', 'archive-linux-variants-build-status.json')
source = source.replace("step == 'publish local SITL binary'", "step == 'publish all local SITL binaries'")
start = source.index('    for step, args, filename in (')
end = source.index('except Exception:', start)
block = '''    for step, args, filename in (
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
'''
Path(__file__).with_name('build-variants-in-linux-tmp.py').write_text(source[:start] + block + source[end:])
