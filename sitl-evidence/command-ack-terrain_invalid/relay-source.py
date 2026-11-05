"""Pass complete MAVLink frames; selectively drop GET_MESSAGE_INTERVAL ACKs."""
import hashlib
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import time
import traceback
import sys

base = Path(__file__).resolve().parent
case = os.environ['SITL_COMMAND_CASE']
instance = int(os.environ['SITL_COMMAND_INSTANCE'])
form = os.environ.get('SITL_COMMAND_FORM', 'long')
if case not in ('normal', 'drop_one', 'drop_all', 'retarget', 'inject_progress', 'inject_progress_sequential', 'inject_progress_drain', 'stale_ack_test', 'terrain_fixture', 'terrain_fixture_stream', 'terrain_slope', 'terrain_invalid', 'calibration_start', 'calibration_step', 'calibration_full', 'calibration_armed', 'calibration_armed_observed', 'calibration_control', 'calibration_control_retry', 'calibration_lifecycle', 'calibration_lifecycle_observed', 'calibration_lifecycle_pumped', 'calibration_page_navigation', 'calibration_page_close', 'calibration_page_close_retry', 'calibration_disposed_callback', 'mode_normal', 'mode_drop_cmd', 'mode_drop_legacy', 'mode_drop_all', 'mode_invalid', 'mode_string', 'mode_string_verified', 'mode_string_invalid') or form not in ('long', 'int', 'unsupported', 'mode') or not 124 <= instance <= 170:
    raise ValueError('invalid test case or instance')
if case.startswith('mode_') != (form == 'mode'): raise ValueError('mode case/form mismatch')
if case in ('retarget', 'inject_progress', 'inject_progress_sequential', 'inject_progress_drain', 'stale_ack_test') and form not in ('long', 'int'): raise ValueError('invalid injection form')
if case == 'stale_ack_test' and form != 'int': raise ValueError('stale ACK case requires COMMAND_INT')
run = base / (('flight-mode-' + case[5:]) if form == 'mode' else
              ('command-target-live-' + form) if case == 'retarget' else
              'command-stale-ack-int' if case == 'stale_ack_test' else
              ('command-progress-drain-' + form) if case == 'inject_progress_drain' else
              ('command-progress-sequential-' + form) if case == 'inject_progress_sequential' else
              ('command-progress-live-' + form) if case == 'inject_progress' else
              (('command-unsupported-' if form == 'unsupported' else 'command-int-ack-' if form == 'int' else 'command-ack-') + case))
run.mkdir(exist_ok=False)
binary = base / 'archive-built/arducopter'
sitl_port = 5760 + 10 * instance
proxy_port = sitl_port + 1
result = {'scope': ('Disposable Copter SITL; synthetic terrain fixture; no deliberate packet loss' if case in ('terrain_fixture', 'terrain_fixture_stream', 'terrain_slope', 'terrain_invalid') else
                    'Disposable Copter SITL; calibration lifecycle interaction; no deliberate packet loss' if case in ('calibration_armed', 'calibration_armed_observed', 'calibration_control', 'calibration_control_retry', 'calibration_lifecycle', 'calibration_lifecycle_observed', 'calibration_lifecycle_pumped', 'calibration_page_navigation', 'calibration_page_close', 'calibration_page_close_retry', 'calibration_disposed_callback') else
                    'Disposable disarmed Copter SITL; accelerometer calibration interaction; no deliberate packet loss' if case in ('calibration_start', 'calibration_step', 'calibration_full') else
                    'Disposable disarmed Copter SITL; relay selectively drops mode-setting messages' if form == 'mode' else
                    'Disposable source-built Copter SITL; relay inserts progress, shifts first ACK and drops second ACK' if case == 'stale_ack_test' else
                    'Disposable source-built Copter SITL; relay inserts progress ACK and shifts accepted ACK sequence' if case in ('inject_progress_sequential', 'inject_progress_drain') else
                    'Disposable source-built Copter SITL; relay inserts one IN_PROGRESS ACK before the real ACK' if case == 'inject_progress' else
                    'Disposable source-built Copter SITL; relay alters one ACK target and recalculates checksum' if case == 'retarget' else
                    'Disposable source-built Copter SITL; unsupported command ID; no deliberate ACK loss' if form == 'unsupported'
                    else 'Disposable source-built Copter SITL; read-only interval request; targeted downlink ACK loss'),
          'case': case, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
          'sitl_port': sitl_port, 'proxy_port': proxy_port, 'requests': [], 'dropped_acks': 0,
          'stray_bytes': {'to_client': 0, 'to_sitl': 0}, 'errors': []}
if case == 'stale_ack_test': result['command_events'] = []
if form == 'mode': result['mode_packets'] = {'command_seen': 0, 'command_dropped': 0, 'legacy_seen': 0, 'legacy_dropped': 0}
listener = client = target = proc = log = None
files = {}
if case in ('retarget', 'inject_progress', 'inject_progress_sequential', 'inject_progress_drain', 'stale_ack_test'):
    os.environ['MAVLINK20'] = '1'
    sys.path.insert(0, str(base / 'python'))
    from pymavlink.dialects.v20 import ardupilotmega

def forward(buf, dest, direction):
    while buf:
        magic = buf[0]
        if magic not in (0xfe, 0xfd):
            dest.sendall(buf[:1]); files[direction + '_output'].write(buf[:1]); del buf[:1]
            result['stray_bytes'][direction] += 1
            continue
        header = 6 if magic == 0xfe else 10
        if len(buf) < header: return
        size = buf[1] + (8 if magic == 0xfe else 12)
        if magic == 0xfd and buf[2] & 1: size += 13
        if len(buf) < size: return
        packet = bytes(buf[:size]); del buf[:size]
        msgid = packet[5] if magic == 0xfe else packet[7] | packet[8] << 8 | packet[9] << 16
        payload = packet[header:header + packet[1]]
        if form == 'mode' and direction == 'to_sitl':
            is_command = msgid == 76 and len(payload) >= 30 and int.from_bytes(payload[28:30], 'little') == 176
            is_legacy = msgid == 11
            if is_command or is_legacy:
                kind = 'command' if is_command else 'legacy'
                result['mode_packets'][kind + '_seen'] += 1
                drop = case == 'mode_drop_all' or (is_command and case == 'mode_drop_cmd') or (is_legacy and case == 'mode_drop_legacy')
                if drop:
                    result['mode_packets'][kind + '_dropped'] += 1
                    files['dropped'].write(packet)
                    continue
        if direction == 'to_sitl' and msgid == 76 and len(payload) >= 30:
            padded = payload.ljust(33, b'\0')
            command = int.from_bytes(padded[28:30], 'little')
            if command == 510: result['requests'].append({'confirmation': padded[32], 'target': [padded[30], padded[31]]})
        if direction == 'to_sitl' and msgid == 75 and len(payload) >= 30:
            padded = payload.ljust(35, b'\0')
            command = int.from_bytes(padded[28:30], 'little')
            if command == 510:
                result['requests'].append({'frame': padded[32], 'target': [padded[30], padded[31]]})
                if case == 'stale_ack_test': result['command_events'].append('request' + str(len(result['requests'])))
        if direction == 'to_client' and msgid == 77 and len(payload) >= 2 and int.from_bytes(payload[:2], 'little') == 510:
            if case == 'stale_ack_test' and result.get('injected_acks', 0) and len(result['requests']) >= 2:
                files['dropped'].write(packet)
                result['dropped_acks'] += 1
                result['command_events'].append('second_ack_dropped')
                continue
            if case in ('inject_progress', 'inject_progress_sequential', 'inject_progress_drain', 'stale_ack_test') and result.get('injected_acks', 0) == 0:
                if magic != 0xfd or packet[2] & 1: raise ValueError('expected unsigned MAVLink 2 ACK')
                parser = ardupilotmega.MAVLink(None)
                ack = parser.parse_char(packet)
                if ack is None or ack.get_type() != 'COMMAND_ACK' or ack.command != 510 or ack.result != 0:
                    raise ValueError('expected accepted ACK')
                if (ack.target_system, ack.target_component) != (255, 190): raise ValueError('unexpected ACK target')
                files['original_ack'].write(packet)
                sender = ardupilotmega.MAVLink(None, srcSystem=ack.get_srcSystem(), srcComponent=ack.get_srcComponent())
                sender.seq = ack.get_seq()
                ack.result = 5
                injected = ack.pack(sender)
                files['injected_ack'].write(injected)
                dest.sendall(injected)
                files[direction + '_output'].write(injected)
                result['injected_acks'] = 1
                if case in ('inject_progress_sequential', 'inject_progress_drain', 'stale_ack_test'):
                    ack.result = 0
                    sender.seq = (sender.seq + 1) & 255
                    packet = ack.pack(sender)
                    files['modified_ack'].write(packet)
                    result['shifted_acks'] = 1
                    if case == 'stale_ack_test': result['command_events'].append('first_progress_and_accepted_forwarded')
            if case == 'retarget' and result.get('retargeted_acks', 0) == 0:
                if magic != 0xfd or packet[2] & 1: raise ValueError('expected unsigned MAVLink 2 ACK')
                parser = ardupilotmega.MAVLink(None)
                ack = parser.parse_char(packet)
                if ack is None or ack.get_type() != 'COMMAND_ACK' or ack.command != 510:
                    raise ValueError('cannot decode target ACK')
                if (ack.target_system, ack.target_component) != (255, 190):
                    raise ValueError('unexpected original ACK target')
                files['original_ack'].write(packet)
                result['original_ack'] = {'source': [ack.get_srcSystem(), ack.get_srcComponent()],
                                          'target': [ack.target_system, ack.target_component], 'result': ack.result}
                sender = ardupilotmega.MAVLink(None, srcSystem=ack.get_srcSystem(), srcComponent=ack.get_srcComponent())
                sender.seq = ack.get_seq()
                ack.target_system, ack.target_component = 42, 17
                packet = ack.pack(sender)
                files['modified_ack'].write(packet)
                result['retargeted_acks'] = 1
            if case == 'drop_all' or (case == 'drop_one' and result['dropped_acks'] == 0):
                files['dropped'].write(packet)
                result['dropped_acks'] += 1
                continue
        dest.sendall(packet); files[direction + '_output'].write(packet)

try:
    listener = socket.socket(); listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(('127.0.0.1', proxy_port)); listener.listen(1); listener.settimeout(90)
    log = (run / 'sitl.log').open('wb')
    for name in ('to_client_input', 'to_client_output', 'to_sitl_input', 'to_sitl_output', 'dropped'):
        files[name] = (run / (name + '.bin')).open('wb')
    if case in ('retarget', 'inject_progress', 'inject_progress_sequential', 'inject_progress_drain', 'stale_ack_test'):
        for name in ('original_ack', 'modified_ack' if case == 'retarget' else 'injected_ack'):
            files[name] = (run / (name + '.bin')).open('wb')
    if case in ('inject_progress_sequential', 'inject_progress_drain', 'stale_ack_test'):
        files['modified_ack'] = (run / 'modified_ack.bin').open('wb')
    proc = subprocess.Popen([str(binary), '-I', str(instance), '--model', 'calibration' if case == 'calibration_full' else 'quad',
                             '--home=-35.363261,149.165230,584,0'], cwd=run,
                            stdout=log, stderr=subprocess.STDOUT)
    (run / 'ready.json').write_text(json.dumps({'proxy_port': proxy_port}))
    print('READY ' + str(proxy_port), flush=True)
    client, _ = listener.accept()
    deadline = time.monotonic() + 45
    while target is None:
        if proc.poll() is not None: raise RuntimeError('SITL exited during startup')
        try: target = socket.create_connection(('127.0.0.1', sitl_port), timeout=1)
        except OSError:
            if time.monotonic() > deadline: raise
            time.sleep(.25)
    client.settimeout(None); target.settimeout(None)
    buffers = {client: bytearray(), target: bytearray()}
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        readable, _, _ = select.select([client, target], [], [], .5)
        for source in readable:
            chunk = source.recv(65536)
            if not chunk:
                result['closed_by'] = 'client' if source is client else 'sitl'
                break
            direction = 'to_sitl' if source is client else 'to_client'
            files[direction + '_input'].write(chunk); buffers[source].extend(chunk)
            forward(buffers[source], target if source is client else client, direction)
        if result.get('closed_by'): break
    else: raise TimeoutError('relay deadline')
    result['buffered_bytes_at_close'] = sum(map(len, buffers.values()))
except Exception:
    result['errors'].append(traceback.format_exc())
finally:
    for sock in (client, target, listener):
        if sock is not None: sock.close()
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try: proc.wait(timeout=8)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait()
    if log: log.close()
    for stream in files.values(): stream.close()
    result['capture_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in run.glob('*.bin') if p.name != 'eeprom.bin'}
    (run / 'relay-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
if result['errors']: raise SystemExit(1)
