"""Bounded scripted localhost peer for TcpReconnectProbe."""
import hashlib
import json
from pathlib import Path
import socket

root = Path(__file__).resolve().parent.parent
out = root / 'sitl-evidence/tcp-reconnect-probe'
out.mkdir(exist_ok=False)
result = {'scope': 'Synthetic local TCP peer; controlled FIN and explicit reconnect; no vehicle', 'events': [], 'errors': []}
server = socket.socket()
try:
    server.bind(('127.0.0.1', 0))
    server.listen(2)
    server.settimeout(45)
    port = server.getsockname()[1]
    (out / 'ready.json').write_text(json.dumps({'port': port}))
    print('READY ' + str(port), flush=True)
    first, address = server.accept()
    first.settimeout(10)
    result['events'].append('first_accept')
    first.sendall(b'FIRST')
    ack = first.recv(1)
    result['events'].append('first_received=' + ack.hex())
    if ack != b'X': raise ValueError('incorrect marker')
    first.shutdown(socket.SHUT_WR)
    result['events'].append('first_fin_sent')
    while first.recv(64): pass
    result['events'].append('first_client_eof')
    first.close()
    second, address = server.accept()
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
if result['errors']: raise SystemExit(1)
