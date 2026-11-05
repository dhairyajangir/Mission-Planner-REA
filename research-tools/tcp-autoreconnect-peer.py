"""Bounded localhost peer: reset first TCP session, observe next connection."""
import json
from pathlib import Path
import socket
import struct

root = Path(__file__).resolve().parent.parent
out = root / 'sitl-evidence/tcp-autoreconnect-probe'
out.mkdir(exist_ok=False)
result = {'scope': 'Synthetic localhost TCP peer; deliberate RST; no vehicle', 'events': [], 'errors': []}
server = socket.socket()
try:
    server.bind(('127.0.0.1', 0))
    server.listen(2)
    server.settimeout(30)
    (out / 'ready.json').write_text(json.dumps({'port': server.getsockname()[1]}))
    print('READY ' + str(server.getsockname()[1]), flush=True)
    first, _ = server.accept()
    first.settimeout(10)
    result['events'].append('first_accept')
    first.sendall(b'FIRST')
    marker = first.recv(1)
    result['events'].append('first_received=' + marker.hex())
    if marker != b'X': raise ValueError('wrong marker')
    first.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('HH', 1, 0))
    first.close()
    result['events'].append('first_reset')
    second, _ = server.accept()
    second.settimeout(10)
    result['events'].append('second_accept')
    second.sendall(b'SECOND')
    while second.recv(64): pass
    result['events'].append('second_client_eof')
    second.close()
except Exception as exc:
    result['errors'].append(repr(exc))
finally:
    server.close()
    (out / 'peer-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
