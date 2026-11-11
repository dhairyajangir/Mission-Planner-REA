"""Why the GUIDED-mode flight into an empty terrain tile (sitl-terrain-failsafe-midflight.py) stalled instead of triggering the mid-flight failsafe or reaching the gap. A first
attempt here watched AC_WPNav::advance_wp_target_along_track (the multi-leg waypoint-path advancer) and got zero hits all run - it turns out a single ad-hoc GUIDED position
target does not go through AC_WPNav's path-following code at all, only AUTO-style waypoint sequences do. The actual per-loop terrain gate for GUIDED position targets is
ModeGuided::pos_control_run (ArduCopter/mode_guided.cpp): "if (guided_is_terrain_alt && !wp_nav->get_terrain_D_m(terrain_d_m)) { ... copter.failsafe_terrain_on_event(); return; }"
- called every loop, and unlike the mission-based path this calls the failsafe directly, with no 5 s debounce. A hit-count breakpoint on the function's entry plus dprintfs on the
terrain-check line and the failsafe-trigger line show whether that check is ever even reached, and whether it ever actually fails. Simulator only (WSL, gdb, the custom-gcs library).

    python3 sitl-terrain-stall-gdb.py <ardupilot tree> <out dir> <custom-gcs dir>
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
from customgcs import link  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(HOME[0]))
WORK = os.path.expanduser('~/cg-terrain-stall-gdb')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
SPEEDUP = 8
TYPE_MASK_POSITION_ONLY = 0b0000111111111000


def at(north, east):
    return HOME[0] + north / M_LAT, HOME[1] + east / M_LON


FUNCTIONS = ['ModeGuided::pos_control_run', 'Copter::failsafe_terrain_on_event', 'AC_WPNav::get_terrain_D_m', 'AC_WPNav::get_terrain_U_m']


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
        m = re.match(r'\s*\d+\s+breakpoint\s+keep\s+\w\s+0x[0-9a-f]+\s+(?:in\s+(.+?)\s+at\s|<(.+)>\s*$)', line)
        if m:
            current = [re.sub(r'\(.*$', '', m.group(1) or m.group(2)), 0]
            out.append(current)
            continue
        h = re.match(r'\s*breakpoint already hit (\d+) time', line)
        if h and current is not None:
            current[1] = int(h.group(1))
    return out


def start(wipe, under_gdb):
    args = [BIN] + (['-w'] if wipe else []) + ['--model', '+', '-I', '0', '-s', str(SPEEDUP), '--home', '%s,%s,%s,0' % HOME]
    if not under_gdb:
        return subprocess.Popen(args, cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)
    log = open(os.path.join(OUT, 'terrain-stall-gdb.txt'), 'w')
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
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 136, 200000, 0, 0, 0, 0, 0)
        time.sleep(40)
        flight_mode_ok = False
        try:
            from customgcs import flight
            flight.set_mode(conn, 'GUIDED', table='copter')
            armed = flight.arm(conn, timeout=150.0)
            notes.append('arm: %s' % armed.detail)
            flight_mode_ok = armed.ok
        except Exception as e:
            notes.append('arm EXCEPTION %r' % (e,))
        if flight_mode_ok:
            conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, 40.0)
            ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
            notes.append('takeoff ack %s' % (None if ack is None else ack.result))
            time.sleep(20)
            wp = at(0, -19000)
            conn.mav.set_position_target_global_int_send(0, conn.target_system, conn.target_component, mavutil.mavlink.MAV_FRAME_GLOBAL_TERRAIN_ALT_INT, TYPE_MASK_POSITION_ONLY,
                                                          int(wp[0] * 1e7), int(wp[1] * 1e7), 40.0, 0, 0, 0, 0, 0, 0, 0, 0)
            notes.append('SET_POSITION_TARGET_GLOBAL_INT (terrain-alt) sent toward the empty tile')
            time.sleep(200)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    text = open(os.path.join(OUT, 'terrain-stall-gdb.txt'), errors='replace').read()
    hits = parse_hits(text)
    with open(os.path.join(OUT, 'terrain-stall-hits.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n\n' + '\n'.join('%s: %d hits' % (fn, n) for fn, n in hits) + '\n')
    print('[terrain-stall] %s' % hits, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
