"""A small local screen for the prototype: a web page served on this machine only, driving the same library functions as the command line.

    python -m customgcs ui [--port 5760] [--ui-port 8765]

Design:
- One worker thread owns the MAVLink connection (pymavlink connections are not thread-safe). It keeps a state record up to date and runs the commands the page sends, one at a time.
- Every message the library functions read also updates the state, through StateLink, so the screen does not go blind while a command (an arm, a mission upload) is running.
- The server binds 127.0.0.1 only, accepts only a Host header naming this machine, and requires a random token (put into the page when it is served) on every POST: another web page open
  in the same browser cannot drive the vehicle through it.
- The vehicle connection itself is limited to a local simulator exactly as the command line is: the host is always 127.0.0.1.
Simulator use only so far (see README.md).
"""
import json
import math
import os
import queue
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional

from . import flight, link, mission, params
from .vehicle import detect

MAX_TEXTS = 40
MAX_TRACK = 3000
COMMAND_TIMEOUT_S = 150.0


class State:
    """What the screen shows. Written by the worker thread, copied out under a lock."""

    def __init__(self):
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        with self.lock:
            self.connected = False
            self.vehicle = None
            self.table = None
            self.armed = None
            self.mode = None
            self.base_mode = None
            self.position = None            # (lat, lon, relative alt m)
            self.home = None
            self.speed = None
            self.heading = None
            self.battery_v = None
            self.gps = None                 # (fix type, satellites)
            self.attitude = None            # (roll deg, pitch deg)
            self.current_item = None
            self.last_message_at = None
            self.texts: List[str] = []
            self.track: List[tuple] = []
            self.mission_items: List[dict] = []
            self.busy = None
            self.error = None

    def update(self, msg, table: Optional[str]):
        kind = msg.get_type()
        now = time.time()
        with self.lock:
            self.last_message_at = now
            if kind == 'HEARTBEAT' and msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                self.armed = flight.is_armed(msg)
                self.base_mode = msg.base_mode
                self.mode = flight.mode_name(msg.custom_mode, table) if table else 'mode %d' % msg.custom_mode
            elif kind == 'GLOBAL_POSITION_INT':
                if msg.lat == 0 and msg.lon == 0:           # no position yet: do not plot the point at 0, 0
                    return
                self.position = (msg.lat / 1e7, msg.lon / 1e7, msg.relative_alt / 1000.0)
                self.heading = msg.hdg / 100.0 if msg.hdg != 65535 else None
                if self.home is None and msg.lat != 0:
                    self.home = (msg.lat / 1e7, msg.lon / 1e7)
                self.speed = math.hypot(msg.vx, msg.vy) / 100.0
                if not self.track or abs(self.track[-1][0] - self.position[0]) > 1e-7 or abs(self.track[-1][1] - self.position[1]) > 1e-7:
                    self.track.append((self.position[0], self.position[1]))
                    del self.track[:-MAX_TRACK]
            elif kind == 'SYS_STATUS':
                self.battery_v = msg.voltage_battery / 1000.0 if msg.voltage_battery != 65535 else None
            elif kind == 'GPS_RAW_INT':
                self.gps = (msg.fix_type, msg.satellites_visible)
            elif kind == 'ATTITUDE':
                self.attitude = (math.degrees(msg.roll), math.degrees(msg.pitch))
            elif kind == 'MISSION_CURRENT':
                self.current_item = msg.seq
            elif kind == 'STATUSTEXT':
                self.texts.append(msg.text)
                del self.texts[:-MAX_TEXTS]

    def snapshot(self) -> Dict[str, Any]:
        with self.lock:
            age = None if self.last_message_at is None else round(time.time() - self.last_message_at, 1)
            return dict(connected=self.connected, vehicle=self.vehicle, armed=self.armed, mode=self.mode, position=self.position, home=self.home, speed=self.speed, heading=self.heading,
                        battery_v=self.battery_v, gps=self.gps, attitude=self.attitude, current_item=self.current_item, message_age_s=age, texts=list(self.texts[-15:]),
                        track=list(self.track[-1500:]), mission=list(self.mission_items), busy=self.busy, error=self.error,
                        modes=sorted(flight.vehicle_modes(self.table).items(), key=lambda kv: kv[1]) if self.table else [])


class StateLink:
    """Wraps the pymavlink connection. Every message read through it updates the State, whatever the caller asked for; only the requested types are handed back."""

    def __init__(self, conn, state: State, table: Optional[str]):
        self._conn, self._state, self._table = conn, state, table

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def recv_match(self, type=None, blocking=False, timeout=None):
        wanted = None if type is None else ({type} if isinstance(type, str) else set(type))
        end = None if timeout is None else time.time() + timeout
        while True:
            remaining = None if end is None else max(0.0, end - time.time())
            msg = self._conn.recv_match(type=None, blocking=blocking, timeout=min(0.2, remaining) if remaining is not None else 0.2)
            if msg is not None:
                self._state.update(msg, self._table)
                if wanted is None or msg.get_type() in wanted:
                    return msg
            if not blocking or (end is not None and time.time() >= end):
                return None


class Session:
    """The worker thread: owns the connection, keeps the state fresh, runs queued commands."""

    def __init__(self):
        self.state = State()
        self.commands: 'queue.Queue' = queue.Queue()
        self.conn = None
        self.info = None
        self.table = None
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    # ---- called from request threads
    def call(self, fn: Callable[[], Any], label: str) -> Any:
        box = {'done': threading.Event()}
        self.commands.put((fn, label, box))
        if not box['done'].wait(COMMAND_TIMEOUT_S):
            raise TimeoutError('%s did not finish in %.0f s' % (label, COMMAND_TIMEOUT_S))
        if 'error' in box:
            raise box['error']
        return box['result']

    def close(self):
        self.stop.set()

    # ---- worker thread
    def _run(self):
        while not self.stop.is_set():
            try:
                fn, label, box = self.commands.get(timeout=0.05)
            except queue.Empty:
                self._poll()
                continue
            with self.state.lock:
                self.state.busy = label
            try:
                box['result'] = fn()
            except Exception as e:                                  # reported to the page, never swallowed
                box['error'] = e
            with self.state.lock:
                self.state.busy = None
            box['done'].set()

    def _poll(self):
        if self.conn is None:
            return
        try:
            self.conn.recv_match(type=['HEARTBEAT'], blocking=True, timeout=0.2)        # StateLink feeds the state from everything it reads
        except Exception as e:
            with self.state.lock:
                self.state.error = 'connection lost: %s' % e
                self.state.connected = False
            self.conn = None

    # ---- commands (run on the worker thread through call())
    def connect(self, port: int) -> Dict[str, Any]:
        def work():
            self.disconnect_now()
            raw, mav_type = link.connect(port, '127.0.0.1', timeout=20.0)
            parameters = link.read_params(raw)
            info = detect(parameters, mav_type)
            try:
                self.table = flight.table_for(info.kind)
            except KeyError:
                self.table = None
            self.state.reset()
            self.conn = StateLink(raw, self.state, self.table)
            self.info = info
            with self.state.lock:
                self.state.connected = True
                self.state.vehicle = '%s (frame class %s, type %s), %d parameters' % (info.kind, info.frame_class, info.frame_type, len(parameters))
                self.state.table = self.table
            for message_id, interval_us in ((33, 200000), (1, 500000), (24, 500000), (30, 200000), (42, 500000)):
                raw.mav.command_long_send(raw.target_system, raw.target_component, 511, 0, message_id, interval_us, 0, 0, 0, 0, 0)
            self.parameters = parameters
            return {'ok': True, 'detail': 'connected to a %s' % info.kind, 'modes': sorted(flight.vehicle_modes(self.table).items(), key=lambda kv: kv[1]) if self.table else []}
        return self.call(work, 'connecting')

    def disconnect_now(self):
        if self.conn is not None:
            try:
                self.conn._conn.close()
            except Exception:
                pass
        self.conn = None
        self.state.reset()

    def need_vehicle(self):
        if self.conn is None:
            raise RuntimeError('not connected')
        return self.conn

    def result(self, r: flight.Result) -> Dict[str, Any]:
        return {'ok': r.ok, 'detail': r.detail, 'texts': list(r.texts)[-6:]}

    def set_mode(self, name: str):
        return self.call(lambda: self.result(flight.set_mode(self.need_vehicle(), name, table=self.table)), 'setting mode %s' % name)

    def arm(self, force: bool = False):
        return self.call(lambda: self.result(flight.arm(self.need_vehicle(), force=force, timeout=30.0)), 'arming')

    def disarm(self):
        return self.call(lambda: self.result(flight.disarm(self.need_vehicle())), 'disarming')

    def fly_mission(self):
        """Arm, switch to AUTO and start the mission without the pauses a person would add: a Copter that stays armed on the ground for DISARM_DELAY (10 s) without taking off disarms itself."""
        def work():
            conn = self.need_vehicle()
            steps = []
            manual = {'copter': 'STABILIZE', 'plane': 'MANUAL'}.get(self.table)       # a Copter refuses to arm in AUTO ("Auto mode not armable"), so leave AUTO first
            if manual is not None:
                steps.append('%s: %s' % (manual, flight.set_mode(conn, manual, table=self.table).detail))
            armed = flight.arm(conn, timeout=60.0)
            steps.append('arm: ' + armed.detail)
            if not armed.ok:
                return {'ok': False, 'detail': '; '.join(steps), 'texts': list(armed.texts)[-6:]}
            mode = flight.set_mode(conn, 'AUTO', table=self.table)
            give_up = time.time() + 30.0
            while not mode.ok and time.time() < give_up:       # AUTO is refused until the position estimate is ready
                time.sleep(2)
                mode = flight.set_mode(conn, 'AUTO', table=self.table)
            steps.append('AUTO: ' + mode.detail)
            if not mode.ok:
                return {'ok': False, 'detail': '; '.join(steps) + ' (the vehicle stays armed until its own auto-disarm)', 'texts': list(mode.texts)[-6:]}
            if self.table == 'copter':
                started = flight.start_mission(conn)
                steps.append('start: ' + started.detail)
                return {'ok': started.ok, 'detail': '; '.join(steps), 'texts': list(started.texts)[-6:]}
            return {'ok': True, 'detail': '; '.join(steps) + ' (a %s starts its mission when AUTO is entered)' % (self.info.kind if self.info else 'vehicle'), 'texts': list(mode.texts)[-6:]}
        return self.call(work, 'arming, AUTO and mission start')

    def start_mission(self):
        return self.call(lambda: self.result(flight.start_mission(self.need_vehicle())), 'starting the mission')

    def upload(self, wpl: str, list_name: str = 'mission'):
        kind = {'mission': mission.MISSION, 'fence': mission.FENCE, 'rally': mission.RALLY}[list_name]

        def work():
            items = mission.loads_wpl(wpl)
            ack = mission.upload(self.need_vehicle(), items, mission_type=kind)
            if kind == mission.MISSION and ack == 0:
                self._publish_mission(items)
            return {'ok': ack == 0, 'detail': 'uploaded %d items, vehicle answered %s' % (len(items), 'accepted' if ack == 0 else 'refused (type %d)' % ack), 'texts': []}
        return self.call(work, 'uploading')

    def download(self, list_name: str = 'mission'):
        kind = {'mission': mission.MISSION, 'fence': mission.FENCE, 'rally': mission.RALLY}[list_name]

        def work():
            items = mission.download(self.need_vehicle(), mission_type=kind)
            if kind == mission.MISSION:
                self._publish_mission(items)
            return {'ok': True, 'detail': 'downloaded %d items' % len(items), 'wpl': mission.dumps_wpl(items) if items else mission.WPL_HEADER + '\n', 'texts': []}
        return self.call(work, 'downloading')

    def clear(self, list_name: str = 'mission'):
        kind = {'mission': mission.MISSION, 'fence': mission.FENCE, 'rally': mission.RALLY}[list_name]

        def work():
            ack = mission.clear(self.need_vehicle(), mission_type=kind)
            if kind == mission.MISSION:
                self._publish_mission([])
            return {'ok': ack == 0, 'detail': 'clear answered %s' % ('accepted' if ack == 0 else 'type %d' % ack), 'texts': []}
        return self.call(work, 'clearing')

    def _publish_mission(self, items):
        with self.state.lock:
            self.state.mission_items = [{'seq': i.seq, 'command': i.command, 'lat': i.x, 'lon': i.y, 'alt': i.z} for i in items if i.seq > 0 and (i.x or i.y)]

    def parameter_list(self) -> Dict[str, float]:
        return self.call(lambda: link.read_params(self.need_vehicle()), 'reading parameters')

    def set_parameter(self, name: str, value: float):
        def work():
            conn = self.need_vehicle()
            hb = flight.current_heartbeat(conn)
            if hb is not None and flight.is_armed(hb):
                raise RuntimeError('refusing to write parameters while the vehicle is armed')
            current = link.read_params(conn)
            if name not in current:
                raise KeyError('the vehicle has no parameter %s' % name)
            if params.protected(name):
                raise RuntimeError('%s is protected (a link setting or a value the vehicle maintains itself)' % name)
            r = params.write(conn, [params.Change(name, current[name], value)])[0]
            return {'ok': r.ok, 'detail': ('%s is now %.9g (was %.9g)' % (name, r.got, current[name])) if r.ok else '%s: %s' % (name, r.note), 'texts': []}
        return self.call(work, 'writing %s' % name)


# ---- HTTP

LOCAL_HOSTS = ('127.0.0.1', 'localhost')


def make_handler(session: Session, token: str, page: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):        # keep the console quiet
            pass

        def _host_ok(self) -> bool:
            host = (self.headers.get('Host') or '').split(':')[0]
            return host in LOCAL_HOSTS

        def _send(self, code: int, body: bytes, content_type: str = 'application/json'):
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, data: Any):
            self._send(code, json.dumps(data).encode('utf-8'))

        def do_GET(self):
            if not self._host_ok():
                return self._json(403, {'ok': False, 'detail': 'host not allowed'})
            path = self.path.split('?')[0]
            if path == '/':
                return self._send(200, page.replace('__TOKEN__', token).encode('utf-8'), 'text/html; charset=utf-8')
            if path == '/api/state':
                return self._json(200, session.state.snapshot())
            if path == '/api/params':
                try:
                    return self._json(200, session.parameter_list())
                except Exception as e:
                    return self._json(200, {'ok': False, 'detail': str(e.args[0] if isinstance(e, KeyError) and e.args else e)})
            if path == '/api/params.param':
                try:
                    body = params.dumps(session.parameter_list(), 'saved from the screen').encode('utf-8')
                    return self._send(200, body, 'text/plain; charset=utf-8')
                except Exception as e:
                    return self._send(500, str(e).encode('utf-8'), 'text/plain; charset=utf-8')
            self._json(404, {'ok': False, 'detail': 'not found'})

        def do_POST(self):
            length = int(self.headers.get('Content-Length') or 0)
            raw = self.rfile.read(length) if 0 <= length <= 2_000_000 else b''          # read the body first: answering before it is read can reset the client's connection
            if length > 2_000_000:
                return self._json(413, {'ok': False, 'detail': 'request too large'})
            if not self._host_ok():
                return self._json(403, {'ok': False, 'detail': 'host not allowed'})
            if not secrets.compare_digest(self.headers.get('X-Token') or '', token):
                return self._json(403, {'ok': False, 'detail': 'missing or wrong token'})
            try:
                body = json.loads(raw or b'{}')
                path = self.path.split('?')[0]
                if path == '/api/connect':
                    return self._json(200, session.connect(int(body.get('port', 5760))))
                if path == '/api/disconnect':
                    session.call(session.disconnect_now, 'disconnecting')
                    return self._json(200, {'ok': True, 'detail': 'disconnected'})
                if path == '/api/mode':
                    return self._json(200, session.set_mode(str(body['name'])))
                if path == '/api/arm':
                    return self._json(200, session.arm(bool(body.get('force', False))))
                if path == '/api/disarm':
                    return self._json(200, session.disarm())
                if path == '/api/mission/fly':
                    return self._json(200, session.fly_mission())
                if path == '/api/mission/start':
                    return self._json(200, session.start_mission())
                if path == '/api/mission/upload':
                    return self._json(200, session.upload(str(body['wpl']), str(body.get('list', 'mission'))))
                if path == '/api/mission/download':
                    return self._json(200, session.download(str(body.get('list', 'mission'))))
                if path == '/api/mission/clear':
                    return self._json(200, session.clear(str(body.get('list', 'mission'))))
                if path == '/api/param':
                    return self._json(200, session.set_parameter(str(body['name']), float(body['value'])))
                self._json(404, {'ok': False, 'detail': 'not found'})
            except (RuntimeError, ValueError, TimeoutError, KeyError) as e:
                self._json(200, {'ok': False, 'detail': str(e.args[0] if isinstance(e, KeyError) and e.args else e), 'texts': []})
    return Handler


def serve(ui_port: int = 8765, vehicle_port: Optional[int] = None) -> None:
    page = open(os.path.join(os.path.dirname(__file__), 'data', 'ui.html'), encoding='utf-8').read()
    token = secrets.token_urlsafe(16)
    session = Session()
    server = ThreadingHTTPServer(('127.0.0.1', ui_port), make_handler(session, token, page))
    print('screen at http://127.0.0.1:%d/   (this machine only; simulator use only)' % ui_port, flush=True)
    if vehicle_port is not None:
        print('connecting to the simulator on port %d ...' % vehicle_port, flush=True)
        try:
            print(session.connect(vehicle_port)['detail'], flush=True)
        except Exception as e:
            print('could not connect now: %s (use the Connect button)' % e, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        session.close()
        server.server_close()
