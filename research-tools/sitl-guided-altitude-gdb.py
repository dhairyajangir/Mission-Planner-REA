"""Why GUIDED_CHANGE_ALTITUDE has no observed effect (sitl-guided-offboard-control.py, plane_guided_slew and plane_guided_altitude_no_wp): one-shot gdb breakpoints on
ModeGuided::update_target_altitude() (the function that reads the offboard-slewed target, ArduPlane/mode_guided.cpp) and Plane::set_target_altitude_location() (the only place that
applies a new target, ArduPlane/altitude.cpp:218) over the exact scenario of plane_guided_altitude_no_wp(): plain mode switch to GUIDED, no DO_REPOSITION, then one
GUIDED_CHANGE_ALTITUDE to 120 m. If update_target_altitude is never hit, GUIDED's per-loop update is not calling it at all; if it is hit but set_target_altitude_location from inside
it is not, the function's own `if` guard (current_loc/target_location initialised(), get_alt_cm) is failing. Simulator only (WSL, gdb, the custom-gcs library).

    python3 sitl-guided-altitude-gdb.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
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
M_LON = M_LAT * math.cos(math.radians(HOME[0]))
WORK = os.path.expanduser('~/cg-guided-alt-gdb')
BIN = os.path.join(TREE, 'build/sitl/bin/arduplane')
FUNCTIONS = ['ModeGuided::update_target_altitude', 'Plane::set_target_altitude_location', 'Mode::update_target_altitude']


def at(north, east):
    return HOME[0] + north / M_LAT, HOME[1] + east / M_LON


def gdb_script():
    lines = ['set pagination off', 'set confirm off', 'handle SIGALRM SIGUSR1 SIGUSR2 SIGPIPE SIGURG nostop noprint pass']
    for fn in FUNCTIONS:
        lines += ['break %s' % fn, 'commands', 'silent', 'continue', 'end']
    lines += ['run', 'info breakpoints']
    path = os.path.join(WORK, 'gdb-commands.txt')
    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    return path


def parse_hits(text):
    table = text[text.rfind('Num     Type'):] if 'Num     Type' in text else ''
    out, current = [], None
    for line in table.splitlines():
        m = __import__('re').match(r'\s*\d+\s+breakpoint\s+keep\s+\w\s+0x[0-9a-f]+\s+(?:in\s+(.+?)\s+at\s|<(.+)>\s*$)', line)
        if m:
            current = [__import__('re').sub(r'\(.*$', '', m.group(1) or m.group(2)), 0]
            out.append(current)
            continue
        h = __import__('re').match(r'\s*breakpoint already hit (\d+) time', line)
        if h and current is not None:
            current[1] = int(h.group(1))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arduplane'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    log = open(os.path.join(OUT, 'guided-altitude-gdb.txt'), 'w')
    proc = subprocess.Popen(['gdb', '-q', '-batch', '-x', gdb_script(), '--args', BIN, '-w', '--model', 'plane', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    notes = []
    try:
        conn, _ = link.connect(5760, timeout=300.0)
        time.sleep(45)
        a, b = at(300, 0), at(300, 300)
        items = [mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2]), mission.Item(1, 3, 22, 1, 1, 15.0, 0, 0, 0, 0.0, 0.0, 60.0),
                 mission.Item(2, 3, 16, 0, 1, 0, 0, 0, 0, a[0], a[1], 60.0), mission.Item(3, 3, 16, 0, 1, 0, 0, 0, 0, b[0], b[1], 60.0)]
        notes.append('upload ack %s' % mission.upload(conn, items))
        flight.set_mode(conn, 'MANUAL', table='plane')
        armed = flight.arm(conn, timeout=150.0)
        notes.append('arm: %s' % armed.detail)
        auto = flight.set_mode(conn, 'AUTO', table='plane')
        give_up = time.time() + 90.0
        while not auto.ok and time.time() < give_up:
            time.sleep(3)
            auto = flight.set_mode(conn, 'AUTO', table='plane')
        notes.append('AUTO: %s' % auto.detail)
        time.sleep(30)
        guided = flight.set_mode(conn, 'GUIDED', table='plane')
        notes.append('GUIDED: %s' % guided.detail)
        time.sleep(5)
        conn.mav.command_int_send(conn.target_system, conn.target_component, 4, 43001, 0, 0, 0, 0, 3.0, 0, 0, 0, 120.0)  # MAV_FRAME_GLOBAL_RELATIVE_ALT=4
        ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
        notes.append('GUIDED_CHANGE_ALTITUDE to 120 m: ack %s' % (None if ack is None else ack.result))
        time.sleep(60)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arduplane'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    text = open(os.path.join(OUT, 'guided-altitude-gdb.txt'), errors='replace').read()
    hits = parse_hits(text)
    with open(os.path.join(OUT, 'guided-altitude-hits.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n\n' + '\n'.join('%s: %d hits' % (fn, n) for fn, n in hits) + '\n')
    print('[guided-altitude-gdb] %s' % hits, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
