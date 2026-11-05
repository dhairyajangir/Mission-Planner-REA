"""Capture the bytes sent by one local TCP offset probe."""
import json
from pathlib import Path
import socket
root = Path(__file__).resolve().parent.parent
out = root / 'sitl-evidence/tcp-write-offset-probe'
out.mkdir(exist_ok=False)
server = socket.socket()
result = {'scope': 'Synthetic local TCP peer; one buffer slice; no vehicle', 'errors': []}
try:
    server.bind(('127.0.0.1', 0))
    server.listen(1)
    server.settimeout(30)
    (out / 'ready.json').write_text(json.dumps({'port': server.getsockname()[1]}))
    print('READY ' + str(server.getsockname()[1]), flush=True)
    peer, _ = server.accept()
    peer.settimeout(10)
    data = bytearray()
    while True:
        part = peer.recv(1024)
        if not part: break
        data.extend(part)
    peer.close()
    result['bytes_hex'] = bytes(data).hex()
    result['ascii'] = bytes(data).decode('ascii')
except Exception as exc:
    result['errors'].append(repr(exc))
finally:
    server.close()
    (out / 'peer-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
