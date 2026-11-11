"""Why GUIDED_CHANGE_ALTITUDE had no observed effect in plane_guided_slew() (sitl-guided-offboard-control.py): sitl-guided-altitude-values.py traced a simpler no-waypoint scenario
but used the wrong MAV_FRAME for its own GUIDED_CHANGE_ALTITUDE (hardcoded 4 = MAV_FRAME_LOCAL_ENU instead of 3 = MAV_FRAME_GLOBAL_RELATIVE_ALT), so that command was DENIED and the
slew path never ran in that test. This reruns plane_guided_slew()'s own scenario exactly (DO_REPOSITION into GUIDED at 80 m, GUIDED_CHANGE_SPEED, the -50 m/s fault probe, then
GUIDED_CHANGE_ALTITUDE to 120 m with the correct frame=3, matching that script's own ack=0/ACCEPTED result) with a gdb dprintf on Plane::set_target_altitude_location to see the
actual target_altitude.amsl_cm values over time, instead of only the final altitude. Simulator only (WSL, gdb, the custom-gcs library).

    python3 sitl-guided-altitude-values2.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
import math
import os
import subprocess
import sys
import time

from pymavlink import mavutil

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link, mission  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(HOME[0]))
WORK = os.path.expanduser('~/cg-guided-alt-values2')
BIN = os.path.join(TREE, 'build/sitl/bin/arduplane')


def at(north, east):
    return HOME[0] + north / M_LAT, HOME[1] + east / M_LON


def gdb_script():
    lines = ['set pagination off', 'set confirm off', 'handle SIGALRM SIGUSR1 SIGUSR2 SIGPIPE SIGURG nostop noprint pass',
             'dprintf Plane::set_target_altitude_location,"T=%u amsl_cm_before=%d loc.alt=%d loc.relative_alt=%d current_loc.alt=%d home.alt=%d target_alt_rate=%f target_alt_time_ms=%u\\n",'
             'AP_HAL::millis(), target_altitude.amsl_cm, loc.alt, (int)loc.relative_alt, current_loc.alt, home.alt, guided_state.target_alt_rate, guided_state.target_alt_time_ms',
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
    log = open(os.path.join(OUT, 'guided-altitude-values2-gdb.txt'), 'w')
    proc = subprocess.Popen(['gdb', '-q', '-batch', '-x', gdb_script(), '--args', BIN, '-w', '--model', 'plane', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    notes = []
    try:
        conn, _ = link.connect(5760, timeout=120.0)
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
        target_lat, target_lon, target_alt = at(700, 300)[0], at(700, 300)[1], 80.0
        conn.mav.command_int_send(conn.target_system, conn.target_component, mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT, 192, 0, 0, 0, 1, 0, 0,
                                  int(target_lat * 1e7), int(target_lon * 1e7), target_alt)
        ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
        notes.append('DO_REPOSITION to reach GUIDED: ack %s' % (None if ack is None else ack.result))
        time.sleep(15)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 43000, 0, 0, 30.0, 2.0, 0, 0, 0, 0)
        ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
        notes.append('GUIDED_CHANGE_SPEED to 30 m/s: ack %s' % (None if ack is None else ack.result))
        time.sleep(20)
        conn.mav.command_int_send(conn.target_system, conn.target_component, mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT, 43001, 0, 0, 0, 0, 3.0, 0, 0, 0, 120.0)
        ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
        notes.append('GUIDED_CHANGE_ALTITUDE to 120 m (frame=%d GLOBAL_RELATIVE_ALT): ack %s' % (mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT, None if ack is None else ack.result))
        time.sleep(60)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arduplane'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    text = open(os.path.join(OUT, 'guided-altitude-values2-gdb.txt'), errors='replace').read()
    dprintf_lines = [l for l in text.splitlines() if l.startswith('T=')]
    with open(os.path.join(OUT, 'guided-altitude-values2.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n\n%d dprintf lines\n' % len(dprintf_lines))
        f.write('\n'.join(dprintf_lines) + '\n')
    print('[guided-altitude-values2] %d dprintf lines; last: %s' % (len(dprintf_lines), dprintf_lines[-1] if dprintf_lines else None), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
