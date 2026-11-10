"""Copter modes that no ArduPilot autotest names (coverage/copter-mode-test-map.csv: ACRO, DRIFT, SPORT, TURTLE, SYSTEMID, GUIDED_NOGPS), entered in flight in a simulator.
Simulator only (WSL, gdb, the custom-gcs library).

    python3 sitl-copter-untested-modes.py <ardupilot tree> <out dir> <custom-gcs dir>

An AUTO mission (takeoff to 20 m, then a 600 s loiter) holds the Copter in the air; each mode is requested from AUTO, kept for HOLD seconds, then AUTO is requested again. Per mode the
file keeps the vehicle's answer, its texts, the mode its heartbeat reports before and after, and whether the vehicle was still armed. gdb one-shot breakpoints on Mode<X>::init and
Mode<X>::run show which of them the firmware reached.
"""
import json
import math
import os
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link, mission  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
WORK = os.path.expanduser('~/cg-modes')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
HOLD = 8.0
MODES = [('DRIFT', 'ModeDrift'), ('SPORT', 'ModeSport'), ('ACRO', 'ModeAcro'), ('GUIDED_NOGPS', 'ModeGuidedNoGPS'), ('SYSTEMID', 'ModeSystemId'), ('TURTLE', 'ModeTurtle')]
FUNCTIONS = ['%s::%s' % (cls, f) for _, cls in MODES for f in ('init', 'run')]


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


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    log = open(os.path.join(OUT, 'modes-gdb.txt'), 'w')
    proc = subprocess.Popen(['gdb', '-q', '-batch', '-x', gdb_script(), '--args', BIN, '-w', '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    notes, results = [], []
    try:
        conn, _ = link.connect(5760, timeout=300.0)
        time.sleep(45)
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
            for name, cls in MODES:
                before = flight.current_mode(conn)
                r = flight.set_mode(conn, name)
                t = texts(conn, HOLD)
                hb = flight.current_heartbeat(conn)
                results.append({'mode': name, 'class': cls, 'mode_before': before, 'answer': r.detail, 'accepted': r.ok, 'mode_after': flight.mode_name(hb.custom_mode) if hb else None,
                                'armed_after': flight.is_armed(hb) if hb else None, 'texts': t})
                back = flight.set_mode(conn, 'AUTO')
                texts(conn, 3.0)
                notes.append('%s: %s; back to AUTO: %s' % (name, r.detail, back.detail))
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
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
