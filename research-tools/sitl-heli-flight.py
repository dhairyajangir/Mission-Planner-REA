"""The helicopter build (arducopter-heli, frame heli) flown in a simulator, which the earlier runs never managed (arming was refused: "Motor Interlock Enabled"). Simulator only (WSL,
gdb, the custom-gcs library).

    python3 sitl-heli-flight.py <ardupilot tree> <out dir> <custom-gcs dir>

The motor interlock is an RC switch (channel 8 here, by RC override): it must be off to arm and on to run the rotor. Sequence: RC override with channel 8 low, arm in STABILIZE, channel
8 high, wait for the rotor run-up, an AUTO mission (takeoff to 20 m, 600 s loiter) and then ACRO, STABILIZE, ALT_HOLD, LOITER and AUTOROTATE are each requested from AUTO and held
10 s (sticks centred, collective mid). gdb one-shot breakpoints on the helicopter mode and motor functions show what was reached; the vehicle's answers and texts are kept.
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
WORK = os.path.expanduser('~/cg-heli')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter-heli')
HOLD = 10.0
FUNCTIONS = ['AP_MotorsHeli::output_armed_stabilizing', 'AP_MotorsHeli_Single::output_to_motors', 'AC_AttitudeControl_Heli::rate_controller_run', 'ModeStabilize_Heli::init',
             'ModeStabilize_Heli::run', 'ModeAcro_Heli::init', 'ModeAcro_Heli::run', 'ModeAutorotate::init', 'ModeAutorotate::run']
AROT = bool(os.environ.get('HELI_AROT'))                       # HELI_AROT=1: set AROT_ENABLE 1 and request only AUTOROTATE
MODES = ['AUTOROTATE'] if AROT else ['ACRO', 'STABILIZE', 'ALT_HOLD', 'LOITER', 'AUTOROTATE']


def gdb_script():
    lines = ['set pagination off', 'set confirm off', 'handle SIGALRM SIGUSR1 SIGUSR2 SIGPIPE SIGURG nostop noprint pass']
    for fn in FUNCTIONS:
        lines += ['tbreak %s' % fn, 'commands', 'silent', 'printf "HIT %s\\n"' % fn, 'bt 4', 'continue', 'end']
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
    """RC override at 10 Hz: roll, pitch, yaw centred, collective (channel 3) and the interlock switch (channel 8) as set."""

    def __init__(self, conn):
        super().__init__(daemon=True)
        self.conn, self.collective, self.interlock, self.running = conn, 1000, 1000, True

    def run(self):
        while self.running:
            try:
                self.conn.mav.rc_channels_override_send(self.conn.target_system, self.conn.target_component, 1500, 1500, self.collective, 1500, 0, 0, 0, self.interlock)
            except Exception:
                pass
            time.sleep(0.1)


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    log = open(os.path.join(OUT, 'heli-gdb.txt'), 'w')
    proc = subprocess.Popen(['gdb', '-q', '-batch', '-x', gdb_script(), '--args', BIN, '-w', '--model', 'heli', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    notes, results, sticks = [], [], None
    try:
        conn, _ = link.connect(5760, timeout=600.0)
        time.sleep(60)
        p = link.read_params(conn)
        notes.append('frame class %s, RC8_OPTION %s, H_RSC_MODE %s, H_RSC_RUNUP_TIME %s, H_RSC_RAMP_TIME %s' % tuple(p.get(k) for k in ('FRAME_CLASS', 'RC8_OPTION', 'H_RSC_MODE', 'H_RSC_RUNUP_TIME', 'H_RSC_RAMP_TIME')))
        if AROT:
            wanted = ('AROT_ENABLE', 'H_RSC_AROT_ENBL')                # the pre-arm check also wants the rotor-speed controller's autorotation sub-group on
            present = [n for n in wanted if n in p]
            bad = [r.name for r in params.write(conn, [params.Change(n, p.get(n), 1.0) for n in present]) if not r.ok]
            notes.append('set to 1: %s (not present at boot: %s; rejected: %s); before: %s' % (present, [n for n in wanted if n not in p], bad, {n: p.get(n) for n in wanted}))
        sticks = Sticks(conn)
        sticks.start()
        items = [mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2]), mission.Item(1, 3, 22, 1, 1, 0, 0, 0, 0, 0.0, 0.0, 20.0),
                 mission.Item(2, 3, 19, 0, 1, 600.0, 0, 0, 0, HOME[0] + 40 / M_LAT, HOME[1], 20.0)]
        notes.append('upload ack %s' % mission.upload(conn, items))
        notes.append('STABILIZE: %s' % flight.set_mode(conn, 'STABILIZE').detail)
        armed = flight.arm(conn, timeout=150.0)
        notes.append('arm (interlock switch low): %s' % armed.detail)
        notes.extend('vehicle: ' + t for t in texts(conn, 3.0))
        if armed.ok:
            sticks.interlock = 2000
            notes.append('interlock switch raised')
            notes.extend('vehicle: ' + t for t in texts(conn, 25.0))
            auto = flight.set_mode(conn, 'AUTO')
            notes.append('AUTO: %s' % auto.detail)
            notes.append('start: %s' % flight.start_mission(conn).detail)
            notes.extend('vehicle: ' + t for t in texts(conn, 45.0))
            sticks.collective = 1500
            for name in MODES:
                hb = flight.current_heartbeat(conn)
                if hb is None or not flight.is_armed(hb):
                    notes.append('not armed before %s; stopping' % name)
                    break
                before = flight.current_mode(conn)
                r = flight.set_mode(conn, name)
                t = texts(conn, HOLD)
                if not r.ok:
                    notes.append('refusal detail: %s' % r.detail)
                hb = flight.current_heartbeat(conn)
                results.append({'mode': name, 'mode_before': before, 'answer': r.detail, 'accepted': r.ok, 'mode_after': flight.mode_name(hb.custom_mode) if hb else None,
                                'armed_after': flight.is_armed(hb) if hb else None, 'texts': t})
                back = flight.set_mode(conn, 'AUTO')
                texts(conn, 3.0)
                notes.append('%s: %s; back to AUTO: %s' % (name, r.detail, back.detail))
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        if sticks:
            sticks.running = False
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter-heli'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    text = open(os.path.join(OUT, 'heli-gdb.txt'), errors='replace').read()
    hit = [fn for fn in FUNCTIONS if 'HIT %s' % fn in text]
    with open(os.path.join(OUT, 'heli-results.json'), 'w') as f:
        json.dump({'notes': notes, 'modes': results, 'hit': hit, 'not_reached': [fn for fn in FUNCTIONS if fn not in hit]}, f, indent=1)
    print('[heli] hit %d of %d; not reached %s' % (len(hit), len(FUNCTIONS), [fn for fn in FUNCTIONS if fn not in hit]), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
