#!/usr/bin/env python3
"""Bounded, disposable two-SITL test relay; records both directions."""
import hashlib
import json
import os
import select
import socket
import subprocess
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parent
out = root / 'dual-sitl-library-attempt3'
out.mkdir(exist_ok=False)
os.environ['MAVLINK20'] = '1'
sys.path.insert(0, str(root / 'python'))
from pymavlink import mavutil
from pymavlink.dialects.v20 import ardupilotmega

processes, files, sockets = [], [], []
result = {'errors': [], 'dropped_bad_data': [0, 0], 'configured': []}
try:
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(('127.0.0.1', 6980))
    listener.listen(1)
    listener.settimeout(90)
    sockets.append(listener)
    for number, instance, value in [(1, 120, 0), (2, 121, 1)]:
        directory = out / ('vehicle%d' % number)
        directory.mkdir()
        defaults = directory / 'defaults.parm'
        defaults.write_text('MAV_SYSID %d\nLOG_DISARMED %d\n' % (number, value))
        log = open(directory / 'sitl.log', 'wb')
        files.append(log)
        processes.append(subprocess.Popen([str(root / 'archive-built/arducopter'), '-I', str(instance),
            '--model', 'quad', '--defaults', str(defaults), '--home=-35.363261,149.165230,584,0'],
            cwd=directory, stdout=log, stderr=subprocess.STDOUT))
    # Setup clients independently verify the actual source system and parameter value.
    for number, instance, expected in [(1, 120, 0), (2, 121, 1)]:
        port = 5760 + 10 * instance
        deadline = time.monotonic() + 45
        while True:
            try:
                link = mavutil.mavlink_connection('tcp:127.0.0.1:%d' % port, source_system=255)
                break
            except OSError:
                if time.monotonic() > deadline: raise
                time.sleep(.25)
        heartbeat = None
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            heartbeat = link.wait_heartbeat(timeout=2)
            if heartbeat is not None and heartbeat.get_srcSystem() == number: break
        if heartbeat is None or heartbeat.get_srcSystem() != number:
            raise RuntimeError('unexpected heartbeat system for %s: %s' % (number, heartbeat))
        link.mav.param_request_read_send(number, 1, b'LOG_DISARMED', -1)
        deadline = time.monotonic() + 15
        found = None
        while time.monotonic() < deadline:
            msg = link.recv_match(type='PARAM_VALUE', blocking=True, timeout=1)
            if msg and msg.get_srcSystem() == number and msg.param_id == 'LOG_DISARMED':
                found = msg.param_value
                break
        result['configured'].append({'system': number, 'value': found})
        link.close()
        if found != expected: raise RuntimeError('unexpected setup value %s: %s' % (number, found))
    upstream = []
    for instance in (120, 121):
        s = socket.create_connection(('127.0.0.1', 5760 + 10 * instance), timeout=10)
        s.setblocking(False)
        upstream.append(s)
        sockets.append(s)
    parsers = [ardupilotmega.MAVLink(None), ardupilotmega.MAVLink(None)]
    for parser in parsers: parser.robust_parsing = True
    paths = [out / 'upstream1-raw.bin', out / 'upstream2-raw.bin', out / 'downlink.bin', out / 'uplink.bin']
    raw1, raw2, down, up = [open(p, 'wb') for p in paths]
    files.extend([raw1, raw2, down, up])
    (out / 'ready.json').write_text(json.dumps(result, indent=2))
    print('READY', flush=True)
    client, _ = listener.accept()
    client.setblocking(False)
    sockets.append(client)
    deadline = time.monotonic() + 160
    while time.monotonic() < deadline:
        readable, _, _ = select.select([client] + upstream, [], [], 1)
        for s in readable:
            data = s.recv(65536)
            if not data:
                if s is client:
                    result['ended_by'] = 'client_eof'
                    break
                raise RuntimeError('SITL disconnected')
            if s is client:
                up.write(data)
                for target in upstream: target.sendall(data)
            else:
                i = upstream.index(s)
                (raw1 if i == 0 else raw2).write(data)
                for byte in data:
                    msg = parsers[i].parse_char(bytes([byte]))
                    if msg is not None:
                        if msg.get_type() == 'BAD_DATA': result['dropped_bad_data'][i] += 1
                        else:
                            frame = bytes(msg.get_msgbuf())
                            down.write(frame)
                            client.sendall(frame)
        if result.get('ended_by'): break
    else: result['ended_by'] = 'deadline'
except Exception as exc:
    result['errors'].append(repr(exc))
    print('ERROR', repr(exc), flush=True)
finally:
    for s in sockets:
        try: s.close()
        except OSError: pass
    for p in processes:
        p.terminate()
        try: p.wait(timeout=5)
        except subprocess.TimeoutExpired: p.kill(); p.wait()
    for f in files: f.close()
    result['sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob('*.bin')}
    (out / 'relay-result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)
