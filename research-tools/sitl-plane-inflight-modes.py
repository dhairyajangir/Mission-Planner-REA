"""Every ArduPlane flight mode requested in flight, in a QuadPlane simulator (arduplane --model quadplane, so the Q modes exist too). Simulator only (WSL, gdb, the custom-gcs library).

    python3 sitl-plane-modes.py <ardupilot tree> <out dir> <custom-gcs dir>

A mission (VTOL takeoff to 30 m, a waypoint at 60 m, then a 900 s loiter) takes the plane up and through the forward transition; each mode is then requested from AUTO, kept for HOLD
seconds with RC override (roll and pitch centred, throttle mid) and AUTO is requested again. Per mode the file keeps the vehicle's answer, its texts, the mode its heartbeat
reports afterwards and whether it is still armed. gdb one-shot breakpoints on every Mode<X>::_enter / update / run that has a symbol show which functions the firmware reached.
If the plane lands or falls and disarms, it is armed again and the mission restarted from item 1.
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
from customgcs import flight, link, mission  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(35.363261))
WORK = os.path.expanduser('~/cg-pmodes')
BIN = os.path.join(TREE, 'build/sitl/bin/arduplane')
HOLD = 10.0
# (mode name, class, functions with a symbol in the build)
MODES = [('FLY_BY_WIRE_A', 'ModeFBWA', ['update', 'run']), ('FLY_BY_WIRE_B', 'ModeFBWB', ['_enter', 'update']), ('CRUISE', 'ModeCruise', ['_enter', 'update']),
         ('STABILIZE', 'ModeStabilize', ['update', 'run']), ('ACRO', 'ModeAcro', ['_enter', 'update', 'run']), ('MANUAL', 'ModeManual', ['update', 'run']),
         ('TRAINING', 'ModeTraining', ['update', 'run']), ('CIRCLE', 'ModeCircle', ['_enter', 'update']), ('LOITER', 'ModeLoiter', ['_enter', 'update']),
         ('GUIDED', 'ModeGuided', ['_enter', 'update']), ('AVOID_ADSB', 'ModeAvoidADSB', ['_enter', 'update']), ('TAKEOFF', 'ModeTakeoff', ['_enter', 'update']),
         ('THERMAL', 'ModeThermal', ['_enter', 'update']), ('AUTOTUNE', 'ModeAutoTune', ['_enter', 'update', 'run']), ('RTL', 'ModeRTL', ['_enter', 'update']),
         ('AUTOLAND', 'ModeAutoLand', ['_enter', 'update']), ('QSTABILIZE', 'ModeQStabilize', ['_enter', 'update', 'run']), ('QHOVER', 'ModeQHover', ['_enter', 'update', 'run']),
         ('QLOITER', 'ModeQLoiter', ['_enter', 'update', 'run']), ('QACRO', 'ModeQAcro', ['_enter', 'update', 'run']), ('QAUTOTUNE', 'ModeQAutotune', ['_enter', 'update', 'run']),
         ('QRTL', 'ModeQRTL', ['_enter', 'update', 'run']), ('QLAND', 'ModeQLand', ['_enter', 'update', 'run']), ('LOITER_ALT_QLAND', 'ModeLoiterAltQLand', ['_enter'])]
FUNCTIONS = ['%s::%s' % (cls, fn) for _, cls, fns in MODES for fn in fns]


def gdb_script():
    lines = ['set pagination off', 'set confirm off', 'handle SIGALRM SIGUSR1 SIGUSR2 SIGPIPE SIGURG nostop noprint pass']
    for fn in FUNCTIONS:
        lines += ['tbreak %s' % fn, 'commands', 'silent', 'printf "HIT %s\\n"' % fn, 'continue', 'end']
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
    """RC override at 10 Hz: roll, pitch and yaw centred, throttle as set."""

    def __init__(self, conn):
        super().__init__(daemon=True)
        self.conn, self.throttle, self.running = conn, 1000, True

    def run(self):
        while self.running:
            try:
                self.conn.mav.rc_channels_override_send(self.conn.target_system, self.conn.target_component, 1500, 1500, self.throttle, 1500, 0, 0, 0, 0)
            except Exception:
                pass
            time.sleep(0.1)


def at(north, east):
    return HOME[0] + north / M_LAT, HOME[1] + east / M_LON


def launch(conn, sticks, notes):
    """Arm in MANUAL, request AUTO (retry up to 90 s), restart the mission at item 1, and give the plane 60 s to climb and transition."""
    sticks.throttle = 1000
    flight.set_mode(conn, 'MANUAL', table='plane')
    armed = flight.arm(conn, timeout=120.0)
    auto = flight.set_mode(conn, 'AUTO', table='plane')
    give_up = time.time() + 90.0
    while not auto.ok and time.time() < give_up:
        time.sleep(3)
        auto = flight.set_mode(conn, 'AUTO', table='plane')
    conn.mav.mission_set_current_send(conn.target_system, conn.target_component, 1)
    notes.append('launch: %s; %s' % (armed.detail, auto.detail))
    texts(conn, 60.0)
    sticks.throttle = 1500
    return armed.ok and auto.ok


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    log = open(os.path.join(OUT, 'modes-gdb.txt'), 'w')
    proc = subprocess.Popen(['gdb', '-q', '-batch', '-x', gdb_script(), '--args', BIN, '-w', '--model', 'quadplane', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    notes, results, sticks = [], [], None
    try:
        conn, _ = link.connect(5760, timeout=600.0)
        time.sleep(60)
        sticks = Sticks(conn)
        sticks.start()
        items = [mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2]), mission.Item(1, 3, 84, 1, 1, 0, 0, 0, 0, 0.0, 0.0, 30.0),
                 mission.Item(2, 3, 16, 0, 1, 0, 0, 0, 0, at(250, 0)[0], at(250, 0)[1], 60.0), mission.Item(3, 3, 19, 0, 1, 900.0, 0, 0, 0, at(250, 250)[0], at(250, 250)[1], 60.0)]
        notes.append('upload ack %s' % mission.upload(conn, items))
        launched = launch(conn, sticks, notes)
        for name, cls, _ in MODES:
            if not launched:
                break
            hb = flight.current_heartbeat(conn)
            if hb is None or not flight.is_armed(hb):
                launched = launch(conn, sticks, notes)
                if not launched:
                    break
            before = flight.current_mode(conn, table='plane')
            r = flight.set_mode(conn, name, table='plane')
            t = texts(conn, HOLD)
            hb = flight.current_heartbeat(conn)
            results.append({'mode': name, 'class': cls, 'mode_before': before, 'answer': r.detail, 'accepted': r.ok, 'mode_after': flight.mode_name(hb.custom_mode, 'plane') if hb else None,
                            'armed_after': flight.is_armed(hb) if hb else None, 'texts': t})
            back = flight.set_mode(conn, 'AUTO', table='plane')
            texts(conn, 3.0)
            notes.append('%s: %s; back to AUTO: %s' % (name, r.detail, back.detail))
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        if sticks:
            sticks.running = False
        subprocess.call(['pkill', '-TERM', '-x', 'arduplane'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    text = open(os.path.join(OUT, 'modes-gdb.txt'), errors='replace').read()
    hit = [fn for fn in FUNCTIONS if 'HIT %s' % fn in text]
    with open(os.path.join(OUT, 'modes-results.json'), 'w') as f:
        json.dump({'notes': notes, 'modes': results, 'hit': hit, 'not_reached': [fn for fn in FUNCTIONS if fn not in hit]}, f, indent=1)
    print('[plane-modes] hit %d of %d; not reached: %s' % (len(hit), len(FUNCTIONS), [fn for fn in FUNCTIONS if fn not in hit]), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
