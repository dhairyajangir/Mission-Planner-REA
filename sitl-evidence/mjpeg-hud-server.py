"""Serve a labeled synthetic MJPEG image to a local Mission Planner test copy."""
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import time
import traceback
from PIL import Image, ImageDraw

run_name = os.environ.get('MJPEG_HUD_RUN', 'mjpeg-hud-ui')
if Path(run_name).name != run_name:
    raise ValueError('invalid run name')
run = Path(__file__).resolve().parent / run_name
run.mkdir(exist_ok=True)
if (run / 'server-result.json').exists():
    raise FileExistsError('refusing to overwrite prior evidence')
fixture = run / 'synthetic-hud.jpg'
image = Image.new('RGB', (640, 480), (30, 50, 190))
draw = ImageDraw.Draw(image)
draw.rectangle((0, 0, 319, 239), fill=(220, 30, 30))
draw.rectangle((320, 240, 639, 479), fill=(25, 185, 55))
draw.rectangle((80, 185, 560, 295), fill=(250, 220, 30))
draw.text((210, 225), 'SYNTHETIC VIDEO', fill=(0, 0, 0), stroke_width=1)
image.save(fixture, format='JPEG', quality=95)
result = {'scope': 'synthetic MJPEG fixture on localhost only', 'requests': 0, 'frames_sent': 0,
          'fixture_sha256': hashlib.sha256(fixture.read_bytes()).hexdigest(), 'errors': []}


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
        data = fixture.read_bytes()
        deadline = time.monotonic() + 180
        try:
            while time.monotonic() < deadline and not (run / 'stop.txt').exists():
                self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ' +
                                 str(len(data)).encode('ascii') + b'\r\n\r\n' + data + b'\r\n')
                self.wfile.flush()
                result['frames_sent'] += 1
                time.sleep(.4)
        except (BrokenPipeError, ConnectionResetError):
            result['client_closed'] = True


server = None
try:
    server = HTTPServer(('127.0.0.1', 6691), Handler)
    server.timeout = 60
    (run / 'server-ready.txt').write_text('localhost listener ready\n')
    server.handle_request()
except Exception:
    result['errors'].append(traceback.format_exc())
finally:
    if server:
        server.server_close()
    result['passed'] = not result['errors'] and result['requests'] == 1 and result['frames_sent'] >= 1
    (run / 'server-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
if not result['passed']:
    raise SystemExit(1)
