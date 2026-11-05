"""Reset one local connection after receiving an initial marker."""
import json
from pathlib import Path
import socket
import struct
root = Path(__file__).resolve().parent.parent
out = root / 'sitl-evidence/tcp-reset-write-probe'
out.mkdir(exist_ok=False)
server = socket.socket()
result = {'scope': 'Synthetic local TCP peer; reset after marker; no vehicle', 'events': [], 'errors': []}
try:
    server.bind(('127.0.0.1', 0)); server.listen(1); server.settimeout(30)
    (out / 'ready.json').write_text(json.dumps({'port': server.getsockname()[1]}))
    print('READY ' + str(server.getsockname()[1]), flush=True)
    peer, _ = server.accept(); peer.settimeout(10)
    result['events'].append('accepted')
    peer.sendall(b'FIRST')
    marker = peer.recv(1)
    result['events'].append('marker=' + marker.hex())
    if marker != b'X': raise ValueError('wrong marker')
    peer.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('HH', 1, 0))
    peer.close(); result['events'].append('reset')
except Exception as exc:
    result['errors'].append(repr(exc))
finally:
    server.close()
    (out / 'peer-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
