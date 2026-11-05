"""Relay two sequential sessions to a disposable SITL and force one local reset."""
import hashlib
import json
from pathlib import Path
import select
import socket
import struct
import subprocess
import time
import traceback

base = Path(__file__).resolve().parent
run = base / 'mavlink-reconnect-probe'
run.mkdir(exist_ok=False)
binary = base / 'archive-built/arducopter'
result = {'scope': 'Original library through test TCP relay to one disposable source-built Copter SITL',
          'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'events': [], 'errors': []}
process = listener = client = upstream = None
streams = []
try:
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(('127.0.0.1', 6990))
    listener.listen(2)
    listener.settimeout(90)
    simlog = (run / 'sitl.log').open('wb')
    streams.append(simlog)
    process = subprocess.Popen([str(binary), '-I', '122', '--model', 'quad',
                                '--home=-35.363261,149.165230,584,0'], cwd=run,
                               stdout=simlog, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 45
    while True:
        if process.poll() is not None: raise RuntimeError('SITL exited during start')
        try:
            probe = socket.create_connection(('127.0.0.1', 6980), timeout=1)
            probe.close()
            break
        except OSError:
            if time.monotonic() > deadline: raise
            time.sleep(.25)
    (run / 'ready.json').write_text(json.dumps({'proxy_port': 6990}))
    print('READY 6990', flush=True)
    for session in (1, 2):
        client, _ = listener.accept()
        upstream = socket.create_connection(('127.0.0.1', 6980), timeout=10)
        client.settimeout(None); upstream.settimeout(None)
        result['events'].append('session%d_accept' % session)
        uplink = (run / ('uplink%d.bin' % session)).open('wb')
        downlink = (run / ('downlink%d.bin' % session)).open('wb')
        streams.extend([uplink, downlink])
        deadline = time.monotonic() + 100
        while time.monotonic() < deadline:
            if session == 1 and (run / 'drop.request').exists():
                client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                client.close(); client = None
                upstream.close(); upstream = None
                result['events'].append('session1_reset')
                (run / 'drop.ack').write_text('reset\n')
                break
            readable, _, _ = select.select([client, upstream], [], [], .1)
            for source in readable:
                data = source.recv(65536)
                if not data:
                    if session == 2 and source is client:
                        result['events'].append('session2_client_eof')
                        break
                    raise RuntimeError('unexpected peer EOF in session %d' % session)
                if source is client: uplink.write(data); upstream.sendall(data)
                else: downlink.write(data); client.sendall(data)
            if session == 2 and 'session2_client_eof' in result['events']: break
        else: raise TimeoutError('relay session timeout')
        if client: client.close(); client = None
        if upstream: upstream.close(); upstream = None
        uplink.close(); downlink.close()
except Exception:
    result['errors'].append(traceback.format_exc())
finally:
    for sock in (client, upstream, listener):
        if sock is not None: sock.close()
    if process is not None and process.poll() is None:
        process.terminate()
        try: process.wait(timeout=8)
        except subprocess.TimeoutExpired: process.kill(); process.wait()
    for stream in streams:
        if not stream.closed: stream.close()
    result['captures_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in run.glob('*.bin')}
    (run / 'relay-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
if result['errors']: raise SystemExit(1)
