"""Run disposable Copter SITL with targeted MAVLink downlink loss.

For this single failure-injection test, all other complete MAVLink frames are
forwarded unchanged. TCP framing is reconstructed independently in each
direction; an unexpected non-frame prefix is forwarded and counted.
"""
import hashlib
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import time
import traceback

base = Path(__file__).resolve().parent
binary = base / 'archive-built/arducopter'
run_name = os.environ.get('MP_FTP_RUN', 'archive-param-ftp-drop')
if Path(run_name).name != run_name:
    raise ValueError('invalid run name')
instance = int(os.environ.get('MP_FTP_INSTANCE', '85'))
mode = os.environ.get('MP_DROP_MODE', 'ftp_replies')
if mode not in ('ftp_replies', 'param_values', 'param_bulk', 'param_repeat', 'mission_request', 'mission_ack'):
    raise ValueError('unknown drop mode')
sitl_port = 5760 + instance * 10
client_port = sitl_port - 10
run = base / run_name
run.mkdir(exist_ok=True)
out = run / 'proxy-result.json'
if out.exists() or (run / 'sitl.log').exists():
    raise FileExistsError('refusing to overwrite prior test evidence')
result = {'scope': 'local disposable Copter SITL and one TCP client; targeted downlink packet loss', 'mode': mode,
          'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
          'client_port': client_port, 'sitl_port': sitl_port, 'ftp_replies_dropped': 0,
          'ftp_requests_forwarded': 0, 'stray_bytes': 0, 'frames_to_client': 0,
          'frames_to_sitl': 0, 'stray_hex': {'to_client': '', 'to_sitl': ''},
          'param_list_started': False, 'dropped_param_indexes': [], 'mission_upload_started': False,
          'mission_requests_dropped': 0, 'mission_final_item_sent': False, 'mission_acks_dropped': 0, 'errors': []}
proc = listener = client = target = log = None
streams = {}


def forward_frames(buf, dest, direction):
    while buf:
        magic = buf[0]
        if magic not in (0xfe, 0xfd):
            chunk = bytes(buf[:1])
            dest.sendall(chunk)
            streams[direction + '_output'].write(chunk)
            del buf[:1]
            result['stray_bytes'] += 1
            result['stray_hex'][direction] += chunk.hex()
            continue
        header = 6 if magic == 0xfe else 10
        if len(buf) < header:
            return
        length = buf[1] + (8 if magic == 0xfe else 12)
        if magic == 0xfd and buf[2] & 1:
            length += 13
        if len(buf) < length:
            return
        msgid = buf[5] if magic == 0xfe else buf[7] | buf[8] << 8 | buf[9] << 16
        packet = bytes(buf[:length])
        del buf[:length]
        if msgid == 21 and direction == 'to_sitl':
            result['param_list_started'] = True
        if msgid == 44 and direction == 'to_sitl' and packet[1] >= 2:
            payload_offset = 6 if magic == 0xfe else 10
            if int.from_bytes(packet[payload_offset:payload_offset+2], 'little') == 2:
                result['mission_upload_started'] = True
        if (mode == 'mission_request' and direction == 'to_client' and msgid in (40, 51) and
                result['mission_upload_started'] and result['mission_requests_dropped'] == 0):
            result['mission_requests_dropped'] += 1
            streams['dropped'].write(packet)
            continue
        if direction == 'to_sitl' and msgid in (39, 73) and packet[1] >= 30:
            payload_offset = 6 if magic == 0xfe else 10
            if int.from_bytes(packet[payload_offset+28:payload_offset+30], 'little') == 1:
                result['mission_final_item_sent'] = True
        if (mode == 'mission_ack' and direction == 'to_client' and msgid == 47 and
                result['mission_final_item_sent'] and result['mission_acks_dropped'] == 0):
            result['mission_acks_dropped'] += 1
            streams['dropped'].write(packet)
            continue
        if msgid == 110 and direction == 'to_client' and mode == 'ftp_replies':
            result['ftp_replies_dropped'] += 1
            streams['dropped'].write(packet)
            continue
        if msgid == 22 and direction == 'to_client' and mode in ('param_values', 'param_bulk', 'param_repeat') and result['param_list_started']:
            payload_offset = 6 if magic == 0xfe else 10
            if packet[1] >= 8:
                index = int.from_bytes(packet[payload_offset + 6:payload_offset + 8], 'little')
                selected = ((20 <= index < 30 and index not in result['dropped_param_indexes']) if mode == 'param_values'
                            else (0 <= index < 500 and index not in result['dropped_param_indexes']) if mode == 'param_bulk'
                            else (index == 20 and result['dropped_param_indexes'].count(20) < 3))
                if selected:
                    result['dropped_param_indexes'].append(index)
                    streams['dropped'].write(packet)
                    continue
        if msgid == 110 and direction == 'to_sitl':
            result['ftp_requests_forwarded'] += 1
        dest.sendall(packet)
        streams[direction + '_output'].write(packet)
        result['frames_' + direction] += 1


try:
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(('127.0.0.1', client_port))
    listener.listen(1)
    listener.settimeout(120)
    log = (run / 'sitl.log').open('wb')
    for name in ('to_client_input', 'to_client_output', 'to_sitl_input', 'to_sitl_output', 'dropped'):
        streams[name] = (run / (name + '.bin')).open('wb')
    proc = subprocess.Popen([str(binary), '-I', str(instance), '--model', 'quad',
                             '--home=-35.363261,149.165230,584,0'], cwd=run,
                            stdout=log, stderr=subprocess.STDOUT)
    (run / 'ready.txt').write_text('proxy listener ready\n')
    client, _ = listener.accept()
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError('SITL exited before connection')
        try:
            target = socket.create_connection(('127.0.0.1', sitl_port), timeout=1)
            break
        except OSError:
            time.sleep(.5)
    if target is None:
        raise TimeoutError('SITL listener did not open')
    deadline = time.monotonic() + 240
    buffers = {client: bytearray(), target: bytearray()}
    while time.monotonic() < deadline:
        readable, _, _ = select.select([client, target], [], [], 1)
        for source in readable:
            chunk = source.recv(65536)
            if not chunk:
                result['closed_by'] = 'client' if source is client else 'sitl'
                break
            direction = 'to_sitl' if source is client else 'to_client'
            streams[direction + '_input'].write(chunk)
            buffers[source].extend(chunk)
            forward_frames(buffers[source], target if source is client else client,
                           direction)
        if result.get('closed_by'):
            break
    else:
        raise TimeoutError('proxy deadline reached')
    result['buffered_bytes_at_close'] = sum(map(len, buffers.values()))
except Exception:
    result['errors'].append(traceback.format_exc())
finally:
    for sock in (client, target, listener):
        if sock:
            sock.close()
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
    if log:
        log.close()
    for stream in streams.values():
        stream.close()
    if mode == 'ftp_replies':
        selected_loss = result['ftp_replies_dropped'] > 0 and result['ftp_requests_forwarded'] > 0
    elif mode == 'param_values':
        selected_loss = sorted(result['dropped_param_indexes']) == list(range(20, 30))
    elif mode == 'param_bulk':
        selected_loss = sorted(result['dropped_param_indexes']) == list(range(500))
    elif mode == 'param_repeat':
        selected_loss = result['dropped_param_indexes'] == [20, 20, 20]
    elif mode == 'mission_request':
        selected_loss = result['mission_requests_dropped'] == 1 and result['mission_upload_started']
    else:
        selected_loss = result['mission_acks_dropped'] == 1 and result['mission_final_item_sent']
    result['passed'] = not result['errors'] and selected_loss and result.get('buffered_bytes_at_close') == 0
    out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
if not result['passed']:
    raise SystemExit(1)
