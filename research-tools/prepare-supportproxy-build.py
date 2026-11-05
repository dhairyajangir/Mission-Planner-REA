from pathlib import Path
root = Path(__file__).resolve().parent.parent/'supportproxy-source'
for name in ('regen_headers.sh', 'git-version.sh'):
    path = root/name
    raw = path.read_bytes()
    path.write_bytes(raw.replace(b'\r\n', b'\n'))
