"""Preserve the interrupted build evidence and use separate retry files."""
from pathlib import Path

root = Path(__file__).resolve().parent
source = (root / 'build-extras-in-linux-tmp.py').read_text()
source = source.replace('archive-linux-extras-build-status.json', 'archive-linux-extras-retry-build-status.json')
source = source.replace('archive-linux-extras-configure.log', 'archive-linux-extras-retry-configure.log')
source = source.replace("f'archive-linux-{name}-build.log'", "f'archive-linux-{name}-retry-build.log'")
source = source.replace("name, '-j', '2'", "name, '-j', '1'")
target = root / 'build-extras-retry-in-linux-tmp.py'
if target.exists():
    raise FileExistsError(target)
target.write_text(source)
