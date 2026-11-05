"""Adapt the audited variant builder to the remaining vehicle binaries."""
from pathlib import Path

folder = Path(__file__).resolve().parent
source = (folder / 'build-variants-in-linux-tmp.py').read_text()
source = source.replace('archive-linux-variants-build-status.json', 'archive-linux-extras-build-status.json')
source = source.replace('archive-linux-variants-configure.log', 'archive-linux-extras-configure.log')
source = source.replace("('plane', 'rover', 'sub')", "('blimp', 'antennatracker')")
source = source.replace("('ardu' + name)", "name")
(folder / 'build-extras-in-linux-tmp.py').write_text(source)
