"""Serve synthetic JPEG frames over localhost for one MJPEG reader test."""
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import socket
import time
import traceback
from PIL import Image

scenario = os.environ.get('MJPEG_SCENARIO', 'normal')
if scenario not in ('normal', 'missing_length', 'truncated_body'):
    raise ValueError('unknown MJPEG scenario')
run_name = {'normal': 'mjpeg-capture-probe', 'missing_length': 'mjpeg-missing-length',
            'truncated_body': 'mjpeg-truncated-body'}[scenario]
run_name = os.environ.get('MJPEG_RUN_NAME', run_name)
if Path(run_name).name != run_name:
    raise ValueError('invalid run name')
run = Path(__file__).resolve().parent / run_name
run.mkdir(exist_ok=True)
result_file = run / 'server-result.json'
if result_file.exists():
    raise FileExistsError('refusing to overwrite prior evidence')
result = {'scope': 'synthetic MJPEG frames served on 127.0.0.1 only', 'scenario': scenario, 'requests': 0,
          'frames_sent': 0, 'fixture_sha256': [], 'errors': []}
for name, color in [('red', (255, 0, 0)), ('green', (0, 255, 0)), ('blue', (0, 0, 255))]:
    path = run / (name + '.jpg')
    Image.new('RGB', (16, 16), color).save(path, format='JPEG', quality=95)
    result['fixture_sha256'].append({'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass
    def do_GET(self):
        result['requests'] += 1
        if self.path != '/video':
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
        self.end_headers()
        try:
            if scenario == 'missing_length' and result['requests'] == 1:
                data = (run / result['fixture_sha256'][0]['file']).read_bytes()
                self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + data + b'\r\n')
                self.wfile.flush()
                result['frames_sent'] += 1
                return
            if scenario == 'truncated_body':
                data = (run / result['fixture_sha256'][0]['file']).read_bytes()
                self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ' +
                                 str(len(data) + 50).encode('ascii') + b'\r\n\r\n' + data)
                self.wfile.flush()
                result['frames_sent'] += 1
                return
            for fixture in result['fixture_sha256']:
                data = (run / fixture['file']).read_bytes()
                self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ' +
                                 str(len(data)).encode('ascii') + b'\r\n\r\n' + data + b'\r\n')
                self.wfile.flush()
                result['frames_sent'] += 1
                time.sleep(.4)
        except (BrokenPipeError, ConnectionResetError):
            result['client_closed'] = True


server = None
try:
    server = HTTPServer(('127.0.0.1', 6690), Handler)
    server.timeout = 45
    (run / 'ready.txt').write_text('localhost listener ready\n')
    for _ in range(2 if scenario == 'missing_length' else 1):
        server.handle_request()
except Exception:
    result['errors'].append(traceback.format_exc())
finally:
    if server:
        server.server_close()
    expected_requests = 2 if scenario == 'missing_length' else 1
    expected_frames = {'normal': 3, 'missing_length': 4, 'truncated_body': 1}[scenario]
    result['passed'] = not result['errors'] and result['requests'] == expected_requests and result['frames_sent'] == expected_frames
    result_file.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
if not result['passed']:
    raise SystemExit(1)
