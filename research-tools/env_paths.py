"""Machine-specific paths for research tools. Override with env vars (see env.example).

Import what you need: `from env_paths import NODE, ROOT, wsl_path`.
Nothing here raises on a missing tool; the calling subprocess fails with a clear error instead.
"""
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Node.js used to run research-tools/node_modules/rea-agents (REA).
NODE = Path(os.environ.get('MPREA_NODE') or shutil.which('node') or 'node')

# Source-text index databases (ardupilot-source-index.sqlite etc., ~610 MB). They are NOT stored in this repo;
# the verifier and index builders read/write them here. Default: ./integration-research, else the parent folder's.
INTEGRATION_DIR = Path(os.environ.get('MPREA_INTEGRATION_DIR') or next(
    (d for d in (ROOT / 'integration-research', ROOT.parent / 'integration-research') if d.is_dir()),
    ROOT / 'integration-research'))

# Original ArduPilot ZIP used only by verify-ardupilot-archive.py (not stored in this repo).
ARDUPILOT_ZIP = Path(os.environ.get('MPREA_ARDUPILOT_ZIP') or ROOT / 'ardupilot-master.zip')

# LD_PRELOAD shim for SupportProxy loopback tests. Build from supportproxy-loopback-bind.c in WSL:
#   gcc -shared -fPIC -o supportproxy-loopback-bind.so supportproxy-loopback-bind.c -ldl
SUPPORTPROXY_BIND_SHIM = Path(os.environ.get('MPREA_SUPPORTPROXY_BIND_SHIM')
                              or ROOT / 'research-tools/supportproxy-loopback-bind.so')


def wsl_path(path) -> str:
    """Convert C:\\a\\b to /mnt/c/a/b for commands run through wsl.exe."""
    p = Path(path).resolve()
    drive = p.drive.rstrip(':').lower()
    return '/mnt/' + drive + '/' + '/'.join(p.parts[1:])
