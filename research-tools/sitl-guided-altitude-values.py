"""Why GUIDED_CHANGE_ALTITUDE has no observed effect, continued: sitl-guided-altitude-gdb.py confirmed both ModeGuided::update_target_altitude and Plane::set_target_altitude_location
are hit repeatedly, but not what value they settle on. This reruns the exact same no-waypoint GUIDED_CHANGE_ALTITUDE scenario with a gdb `dprintf` on
Plane::set_target_altitude_location printing the computed target_altitude.amsl_cm, the raw loc.alt and relative_alt it was given, current_loc.alt and home.alt on every call (auto-
continuing, not a stop), to see whether the target actually climbs toward 120 m (12000 cm above home) or gets stuck. Simulator only (WSL, gdb, the custom-gcs library).

    python3 sitl-guided-altitude-values.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
import math
import os
import re
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link, mission  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(HOME[0]))
WORK = os.path.expanduser('~/cg-guided-alt-values')
BIN = os.path.join(TREE, 'build/sitl/bin/arduplane')


def at(north, east):
    return HOME[0] + north / M_LAT, HOME[1] + east / M_LON


def gdb_script():
    lines = ['set pagination off', 'set confirm off', 'handle SIGALRM SIGUSR1 SIGUSR2 SIGPIPE SIGURG nostop noprint pass',
             'dprintf Plane::set_target_altitude_location,"T=%u amsl_cm_before=%d loc.alt=%d loc.relative_alt=%d current_loc.alt=%d home.alt=%d\\n",'
             'AP_HAL::millis(), target_altitude.amsl_cm, loc.alt, (int)loc.relative_alt, current_loc.alt, home.alt',
             'run']
    path = os.path.join(WORK, 'gdb-commands.txt')
    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    return path


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arduplane'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    log = open(os.path.join(OUT, 'guided-altitude-values-gdb.txt'), 'w')
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
        notes.append('GUIDED_CHANGE_ALTITUDE to 120 m (12000 cm above home): ack %s' % (None if ack is None else ack.result))
        time.sleep(60)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arduplane'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    text = open(os.path.join(OUT, 'guided-altitude-values-gdb.txt'), errors='replace').read()
    dprintf_lines = [l for l in text.splitlines() if l.startswith('T=')]
    with open(os.path.join(OUT, 'guided-altitude-values.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n\n' + '%d dprintf lines, first 3 and last 10:\n' % len(dprintf_lines))
        f.write('\n'.join(dprintf_lines[:3] + (['...'] if len(dprintf_lines) > 13 else []) + dprintf_lines[-10:]) + '\n')
    print('[guided-altitude-values] %d dprintf lines; last: %s' % (len(dprintf_lines), dprintf_lines[-1] if dprintf_lines else None), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
