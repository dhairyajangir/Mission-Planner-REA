"""Copter modes that no ArduPilot autotest names (coverage/copter-mode-test-map.csv: ACRO, DRIFT, SPORT, TURTLE, SYSTEMID, GUIDED_NOGPS), entered in flight in a simulator.
Simulator only (WSL, gdb, the custom-gcs library).

    python3 sitl-copter-untested-modes.py <ardupilot tree> <out dir> <custom-gcs dir>

An AUTO mission (takeoff to 20 m, then a 600 s loiter) holds the Copter in the air; each mode is requested from AUTO (SYSTEMID from STABILIZE, with SID_AXIS 1), kept for HOLD seconds, then AUTO is requested again. RC override holds sticks centred and throttle mid (1500) during the tests; TURTLE is tried disarmed with throttle 1000 (it refuses when armed or when sticks are off centre); GUIDED_NOGPS gets a level attitude target. If the vehicle fell and disarmed it is armed and launched again. Per mode the
file keeps the vehicle's answer, its texts, the mode its heartbeat reports before and after, and whether the vehicle was still armed. gdb one-shot breakpoints on Mode<X>::init and
Mode<X>::run show which of them the firmware reached.
"""
import json
import math
import os
import subprocess
import sys
import threading
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link, mission, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
WORK = os.path.expanduser('~/cg-modes')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
HOLD = 8.0
TURTLE_ONLY = bool(os.environ.get('TURTLE_ONLY'))        # TURTLE_ONLY=1: set SERVO_DSHOT_ESC 1, try TURTLE disarmed, stop
MODES = [('DRIFT', 'ModeDrift'), ('SPORT', 'ModeSport'), ('ACRO', 'ModeAcro'), ('GUIDED_NOGPS', 'ModeGuidedNoGPS'), ('SYSTEMID', 'ModeSystemId'), ('TURTLE', 'ModeTurtle')]
FUNCTIONS = ['%s::%s' % (cls, f) for _, cls in MODES for f in ('init', 'run')]


def gdb_script():
    lines = ['set pagination off', 'set confirm off', 'handle SIGALRM SIGUSR1 SIGUSR2 SIGPIPE SIGURG nostop noprint pass']
    for fn in FUNCTIONS:
        lines += ['tbreak %s' % fn, 'commands', 'silent', 'printf "HIT %s\\n"' % fn, 'bt 4', 'continue', 'end']
    if TURTLE_ONLY:
        lines.insert(2, 'set breakpoint pending on')       # line breakpoints in mode_turtle.cpp resolve only once the program's symbols are loaded (run 1: "No symbol table is loaded")
        # which `return false` of ModeTurtle::init fires: a one-shot breakpoint on each, printing its line number
        src = os.path.join(TREE, 'ArduCopter/mode_turtle.cpp')
        inside = False
        for number, text in enumerate(open(src, errors='replace').read().splitlines(), 1):
            if 'bool ModeTurtle::init' in text:
                inside = True
            elif inside and text.startswith('}'):
                break
            elif inside and 'return false' in text:
                lines += ['tbreak mode_turtle.cpp:%d' % number, 'commands', 'silent', 'printf "TURTLE_RETURN_FALSE line %d\\n"' % number, 'continue', 'end']
    lines += ['run']
    path = os.path.join(WORK, 'gdb-commands.txt')
    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    return path


def texts(conn, seconds):
    out, end = [], time.time() + seconds
    while time.time() < end:
        msg = conn.recv_match(type=['STATUSTEXT'], blocking=True, timeout=0.5)
        if msg is not None:
            out.append(msg.text)
    return out


class Sticks(threading.Thread):
    """RC override at 10 Hz: roll, pitch and yaw centred, throttle as set (1000 = zero), and, when `attitude` is on, a level SET_ATTITUDE_TARGET with 50 % thrust (GUIDED_NOGPS needs it)."""

    def __init__(self, conn):
        super().__init__(daemon=True)
        self.conn, self.throttle, self.attitude, self.running = conn, 1000, False, True

    def run(self):
        while self.running:
            try:
                self.conn.mav.rc_channels_override_send(self.conn.target_system, self.conn.target_component, 1500, 1500, self.throttle, 1500, 0, 0, 0, 0)
                if self.attitude:
                    self.conn.mav.set_attitude_target_send(0, self.conn.target_system, self.conn.target_component, 0b00000111, [1.0, 0.0, 0.0, 0.0], 0.0, 0.0, 0.0, 0.5)
            except Exception:
                pass
            time.sleep(0.1)


def try_mode(conn, sticks, name, cls, results, notes, hold, after='AUTO', throttle=1500, attitude=False):
    before = flight.current_mode(conn)
    sticks.throttle, sticks.attitude = throttle, attitude
    r = flight.set_mode(conn, name)
    t = texts(conn, hold)
    hb = flight.current_heartbeat(conn)
    results.append({'mode': name, 'class': cls, 'mode_before': before, 'answer': r.detail, 'accepted': r.ok, 'mode_after': flight.mode_name(hb.custom_mode) if hb else None,
                    'armed_after': flight.is_armed(hb) if hb else None, 'texts': t})
    sticks.attitude = False
    back = flight.set_mode(conn, after)
    texts(conn, 3.0)
    notes.append('%s: %s; back to %s: %s' % (name, r.detail, after, back.detail))


def ensure_flying(conn, sticks, notes):
    """If the vehicle is on the ground (disarmed after a fall or landing), arm again and restart the AUTO mission; returns once it should be loitering."""
    hb = flight.current_heartbeat(conn)
    if hb is not None and flight.is_armed(hb):
        return
    sticks.throttle = 1000
    flight.set_mode(conn, 'STABILIZE')
    armed = flight.arm(conn, timeout=60.0)
    auto = flight.set_mode(conn, 'AUTO')
    notes.append('re-launch: %s; %s; %s' % (armed.detail, auto.detail, flight.start_mission(conn).detail if armed.ok and auto.ok else 'not started'))
    texts(conn, 40.0)


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    log = open(os.path.join(OUT, 'modes-gdb.txt'), 'w')
    proc = subprocess.Popen(['gdb', '-q', '-batch', '-x', gdb_script(), '--args', BIN, '-w', '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    notes, results, sticks = [], [], None
    try:
        conn, _ = link.connect(5760, timeout=300.0)
        time.sleep(45)
        base = link.read_params(conn)
        changes = [params.Change('SID_AXIS', base.get('SID_AXIS'), 1.0)]
        if TURTLE_ONLY:                                                  # ModeTurtle::enabled() needs a DShot ESC type (SERVO_DSHOT_ESC), which the simulator does not set by default
            changes.append(params.Change('SERVO_DSHOT_ESC', base.get('SERVO_DSHOT_ESC'), 1.0))
        bad = [r.name for r in params.write(conn, changes) if not r.ok]
        notes.append('set %s (rejected: %s)' % ([(c.name, c.new) if hasattr(c, 'new') else c.name for c in changes], bad))
        sticks = Sticks(conn)
        sticks.start()
        time.sleep(3)                                                    # let the override reach the receiver before TURTLE is asked for (the earlier turtle-entry test waited 1 s)
        try_mode(conn, sticks, 'TURTLE', 'ModeTurtle', results, notes, 4.0, after='STABILIZE', throttle=1500 if TURTLE_ONLY else 1000)      # disarmed; runs 1 to 3 held throttle at 1000, but ModeTurtle::init wants every stick (throttle too) at its centre
        if TURTLE_ONLY:
            raise SystemExit
        items = [mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2]),
                 mission.Item(1, 3, 22, 1, 1, 0, 0, 0, 0, 0.0, 0.0, 20.0),
                 mission.Item(2, 3, 19, 0, 1, 600.0, 0, 0, 0, HOME[0] + 40 / M_LAT, HOME[1], 20.0)]
        notes.append('upload ack %s' % mission.upload(conn, items))
        flight.set_mode(conn, 'STABILIZE')
        armed = flight.arm(conn, timeout=150.0)
        notes.append('arm: %s' % armed.detail)
        auto = flight.set_mode(conn, 'AUTO')
        notes.append('AUTO: %s' % auto.detail)
        if armed.ok and auto.ok:
            notes.append('start: %s' % flight.start_mission(conn).detail)
            notes.extend('vehicle: ' + t for t in texts(conn, 40.0))
            plan = [('SYSTEMID', 'ModeSystemId'), ('DRIFT', 'ModeDrift'), ('SPORT', 'ModeSport'), ('ACRO', 'ModeAcro'), ('GUIDED_NOGPS', 'ModeGuidedNoGPS')]
            for name, cls in plan:
                ensure_flying(conn, sticks, notes)
                if name == 'SYSTEMID':
                    sticks.throttle = 1500
                    flight.set_mode(conn, 'STABILIZE')                 # axis 1 needs a mode with manual throttle
                    texts(conn, 3.0)
                try_mode(conn, sticks, name, cls, results, notes, HOLD, after='AUTO', throttle=1500, attitude=(name == 'GUIDED_NOGPS'))
    except SystemExit:
        pass
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        if sticks:
            sticks.running = False
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    text = open(os.path.join(OUT, 'modes-gdb.txt'), errors='replace').read()
    hit = [fn for fn in FUNCTIONS if 'HIT %s' % fn in text]
    with open(os.path.join(OUT, 'modes-results.json'), 'w') as f:
        json.dump({'notes': notes, 'modes': results, 'hit': hit, 'not_reached': [fn for fn in FUNCTIONS if fn not in hit]}, f, indent=1)
    print('[modes] hit %d of %d: %s' % (len(hit), len(FUNCTIONS), hit), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
