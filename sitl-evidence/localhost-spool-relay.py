"""Relay a workspace file spool to a fixed localhost SITL endpoint only."""
import json
import os
from pathlib import Path
import select
import socket
import sys
import time
import traceback

base = Path(__file__).resolve().parent
run_name = os.environ.get('MP_SPOOL_RUN', 'integrated-spool-probe')
if Path(run_name).name != run_name:
    raise ValueError('invalid run directory name')
port = int(os.environ.get('MP_SPOOL_PORT', '6220'))
if not 1024 <= port <= 65535:
    raise ValueError('invalid local port')
spool = base / run_name / 'spool'
spool.mkdir(parents=True, exist_ok=True)
if (spool.parent / 'relay-result.json').exists() or (spool / 'ready.txt').exists():
    raise FileExistsError('refusing to reuse existing spool evidence')
result = {'target': '127.0.0.1:' + str(port), 'to_app_bytes': 0, 'from_app_bytes': 0, 'errors': []}
sock = None
try:
    duration = int(os.environ.get('MP_SPOOL_SECONDS', '110'))
    if not 10 <= duration <= 900:
        raise ValueError('invalid relay duration')
    deadline = time.monotonic() + duration
    while not (spool / 'ready.txt').exists() and time.monotonic() < deadline:
        time.sleep(.05)
    if not (spool / 'ready.txt').exists():
        raise TimeoutError('application spool did not become ready')
    sock = socket.create_connection(('127.0.0.1', port), timeout=10)
    sock.setblocking(False)
    with (spool / 'from-app.bin').open('rb', buffering=0) as source, (spool / 'to-app.bin').open('ab', buffering=0) as target:
        while time.monotonic() < deadline:
            payload = source.read(65536)
            if payload:
                sock.setblocking(True)
                sock.sendall(payload)
                sock.setblocking(False)
                result['from_app_bytes'] += len(payload)
            readable, _, _ = select.select([sock], [], [], .02)
            if readable:
                payload = sock.recv(65536)
                if not payload:
                    break
                target.write(payload)
                result['to_app_bytes'] += len(payload)
            if (spool / 'closed.txt').exists():
                break
except Exception:
    result['errors'].append(traceback.format_exc())
finally:
    if sock:
        sock.close()
    (spool.parent / 'relay-result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
sys.exit(1 if result['errors'] else 0)
