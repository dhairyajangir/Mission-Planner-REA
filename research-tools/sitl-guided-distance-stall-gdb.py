"""Why GUIDED's position target (sitl-terrain-failsafe-midflight.py) stops advancing partway to a far destination: AC_WPNav::advance_wp_target_along_track was ruled out (zero hits;
a position-only SET_POSITION_TARGET_GLOBAL_INT routes through ModeGuided::set_destination, which with the default GUID_OPTIONS (WPNavUsedForPosControl off) uses the direct
pos_control path, not AC_WPNav's path follower - confirmed by ModeGuided::pos_control_run's own 100,007 hits in that test). This traces the actual numbers inside that path: a
periodic printf (every ~2000th call, roughly once a second) of AC_PosControl's own get_pos_desired_NED_m() and get_pos_estimate_NED_m() - the shaped intermediate target and the
vehicle's own position estimate - to see directly whether the shaper keeps advancing the intermediate target towards the 19 km destination or stops, and whether the vehicle's
estimate tracks it. Same scenario as sitl-terrain-stall-gdb.py (GUIDED, no mission, live terrain-relative target 19 km west), shortened hold since the stall was already seen
starting by t=164 s at this speedup. Simulator only (WSL, gdb, the custom-gcs library).

    python3 sitl-guided-distance-stall-gdb.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
import math
import os
import re
import shutil
import subprocess
import sys
import time

from pymavlink import mavutil

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(HOME[0]))
WORK = os.path.expanduser('~/cg-guided-distance-stall')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
SPEEDUP = 8
TYPE_MASK_POSITION_ONLY = 0b0000111111111000


def at(north, east):
    return HOME[0] + north / M_LAT, HOME[1] + east / M_LON


def gdb_script():
    lines = [
        'set pagination off', 'set confirm off', 'handle SIGALRM SIGUSR1 SIGUSR2 SIGPIPE SIGURG nostop noprint pass',
        'set $cnt = 0',
        'break ModeGuided::pos_control_run',
        'commands',
        'silent',
        'set $cnt = $cnt + 1',
        'if $cnt % 2000 == 0',
        'printf "T=%d desired_x=%f desired_y=%f estimate_x=%f estimate_y=%f\\n", $cnt, '
        'copter.pos_control->get_pos_desired_NED_m().x, copter.pos_control->get_pos_desired_NED_m().y, '
        'copter.pos_control->get_pos_estimate_NED_m().x, copter.pos_control->get_pos_estimate_NED_m().y',
        'end',
        'continue',
        'end',
        'run',
    ]
    path = os.path.join(WORK, 'gdb-commands.txt')
    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    return path


def start(wipe, under_gdb):
    args = [BIN] + (['-w'] if wipe else []) + ['--model', '+', '-I', '0', '-s', str(SPEEDUP), '--home', '%s,%s,%s,0' % HOME]
    if not under_gdb:
        return subprocess.Popen(args, cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)
    log = open(os.path.join(OUT, 'guided-distance-stall-gdb.txt'), 'w')
    return subprocess.Popen(['gdb', '-q', '-batch', '-x', gdb_script(), '--args'] + args, cwd=WORK, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arducopter'])
    subprocess.call(['pkill', '-x', 'gdb'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(os.path.join(WORK, 'terrain'))
    src = os.path.join(TREE, 'terrain', 'S36E149.DAT')
    if os.path.isfile(src) and os.path.getsize(src) > 0:
        shutil.copy(src, os.path.join(WORK, 'terrain', 'S36E149.DAT'))
    notes, proc = [], start(True, True)
    try:
        conn, _ = link.connect(5760, timeout=180.0)
        time.sleep(40)
        flight.set_mode(conn, 'GUIDED', table='copter')
        armed = flight.arm(conn, timeout=150.0)
        notes.append('arm: %s' % armed.detail)
        if armed.ok:
            conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, 40.0)
            ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
            notes.append('takeoff ack %s' % (None if ack is None else ack.result))
            time.sleep(20)
            wp = at(0, -19000)
            conn.mav.set_position_target_global_int_send(0, conn.target_system, conn.target_component, mavutil.mavlink.MAV_FRAME_GLOBAL_TERRAIN_ALT_INT, TYPE_MASK_POSITION_ONLY,
                                                          int(wp[0] * 1e7), int(wp[1] * 1e7), 40.0, 0, 0, 0, 0, 0, 0, 0, 0)
            notes.append('SET_POSITION_TARGET_GLOBAL_INT (terrain-alt) sent toward the empty tile, 19 km west')
            time.sleep(220)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    text = open(os.path.join(OUT, 'guided-distance-stall-gdb.txt'), errors='replace').read()
    samples = [l for l in text.splitlines() if l.startswith('T=')]
    with open(os.path.join(OUT, 'guided-distance-stall-samples.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n\n%d samples\n' % len(samples))
        f.write('\n'.join(samples) + '\n')
    print('[guided-distance-stall] %d samples; last 3: %s' % (len(samples), samples[-3:]), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
