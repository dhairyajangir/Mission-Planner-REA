"""Passively relay one localhost library/SITL session and preserve both byte streams."""
import hashlib
import json
from pathlib import Path
import select
import socket
import subprocess
import time
import traceback

base = Path(__file__).resolve().parent
binary = base / 'archive-built/arducopter'
run = base / 'missionplanner-nonfinite-capture'
run.mkdir(exist_ok=True)
if any((run / name).exists() for name in ('ready.json', 'proxy-result.json', 'uplink.bin', 'downlink.bin')):
    raise FileExistsError('refusing to overwrite prior evidence')
result = {'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
          'simulator_port': 6910, 'proxy_port': 6920,
          'scope': 'Passive localhost relay between original library harness and disposable Copter SITL',
          'errors': [], 'bytes': {'uplink': 0, 'downlink': 0}}
process = listener = client = upstream = None
with (run / 'sitl.log').open('wb') as simlog, (run / 'uplink.bin').open('wb') as uplink, (run / 'downlink.bin').open('wb') as downlink:
    try:
        for port in (6910, 6920):
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', port))
        process = subprocess.Popen([str(binary), '-I', '115', '--model', 'quad',
                                    '--home', '-35.363261,149.165230,584,0'], cwd=run,
                                   stdout=simlog, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('simulator exited before readiness')
            with socket.socket() as probe:
                if probe.connect_ex(('127.0.0.1', 6910)) == 0:
                    break
            time.sleep(.5)
        else:
            raise TimeoutError('simulator listener not available')
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(('127.0.0.1', 6920))
        listener.listen(1)
        listener.settimeout(120)
        (run / 'ready.json').write_text(json.dumps(result, indent=2) + '\n')
        print('READY proxy=6920', flush=True)
        client, address = listener.accept()
        if address[0] != '127.0.0.1':
            raise RuntimeError('non-local client rejected')
        upstream = socket.create_connection(('127.0.0.1', 6910), timeout=10)
        upstream.settimeout(None)
        client.settimeout(None)
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            readable, _, _ = select.select([client, upstream], [], [], 1)
            if process.poll() is not None:
                raise RuntimeError('simulator exited during capture')
            for source in readable:
                data = source.recv(65536)
                if not data:
                    result['ended_by'] = 'client_eof' if source is client else 'simulator_eof'
                    break
                target, output, label = (upstream, uplink, 'uplink') if source is client else (client, downlink, 'downlink')
                target.sendall(data)
                output.write(data)
                result['bytes'][label] += len(data)
            if result.get('ended_by'):
                break
        else:
            raise TimeoutError('capture timed out')
    except Exception:
        result['errors'].append(traceback.format_exc())
    finally:
        for sock in (client, upstream, listener):
            if sock is not None:
                sock.close()
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        result['simulator_exit_code'] = process.returncode if process else None
        uplink.flush()
        downlink.flush()
        for label in ('uplink', 'downlink'):
            result[label + '_sha256'] = hashlib.sha256((run / (label + '.bin')).read_bytes()).hexdigest()
        (run / 'proxy-result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2), flush=True)
if result['errors'] or result.get('ended_by') != 'client_eof':
    raise SystemExit(1)
