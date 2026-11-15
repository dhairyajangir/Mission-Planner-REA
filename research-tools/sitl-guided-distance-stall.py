"""Why GUIDED's position target (sitl-terrain-failsafe-midflight.py) stops advancing partway to a far destination: four gdb attempts at printing AC_PosControl's internal
target/estimate values all failed on C++ expression-evaluation quirks specific to this build (AP_HAL::millis() and millis() both unresolvable from mode_guided.cpp, `this` and
`pos_control` unresolvable at the breakpoint's exact stop address, `copter` lacking full type info from that translation unit) - kept as sitl-evidence/guided-distance-stall-run1
through run4. This drops gdb entirely and logs GLOBAL_POSITION_INT (real lat/lon, vx/vy) directly over MAVLink instead, which needs no C++ expression evaluation at all: same
scenario (GUIDED, no mission, one live terrain-relative SET_POSITION_TARGET_GLOBAL_INT 19 km west), watching whether the reported position and ground velocity actually go to
zero together (a genuine stop) or just stop changing in the one proxy (terrain height) the earlier test happened to log. Simulator only (WSL, pymavlink, the custom-gcs library).

    python3 sitl-guided-distance-stall.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
import csv
import math
import os
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
WORK = os.path.expanduser('~/cg-guided-distance-stall2')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
TYPE_MASK_POSITION_ONLY = 0b0000111111111000


def at(north, east):
    return HOME[0] + north / M_LAT, HOME[1] + east / M_LON


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arducopter'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    notes, track = [], []
    proc = subprocess.Popen([BIN, '-w', '--model', '+', '-I', '0', '-s', '8', '--home', '%s,%s,%s,0' % HOME],
                            cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 33, 100000, 0, 0, 0, 0, 0)  # GLOBAL_POSITION_INT at 10 Hz
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
            conn.mav.set_position_target_global_int_send(0, conn.target_system, conn.target_component, mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT, TYPE_MASK_POSITION_ONLY,
                                                          int(wp[0] * 1e7), int(wp[1] * 1e7), 40.0, 0, 0, 0, 0, 0, 0, 0, 0)
            notes.append('SET_POSITION_TARGET_GLOBAL_INT sent toward a point 19 km west, 40 m relative alt (no terrain tiles involved this time, purely a horizontal-progress check)')
            t0 = time.time()
            while time.time() - t0 < 220.0:
                msg = conn.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=1)
                if msg is None:
                    continue
                t = time.time() - t0
                north_m = (msg.lat * 1e-7 - HOME[0]) * M_LAT
                east_m = (msg.lon * 1e-7 - HOME[1]) * M_LON
                track.append([round(t, 1), msg.lat, msg.lon, round(north_m, 1), round(east_m, 1), msg.vx / 100.0, msg.vy / 100.0])
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    with open(os.path.join(OUT, 'guided-distance-stall-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    with open(os.path.join(OUT, 'guided-distance-stall-track.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['seconds', 'lat', 'lon', 'north_m', 'east_m', 'vx_ms', 'vy_ms'])
        w.writerows(track)
    last = track[-1] if track else None
    speed = None
    if last:
        speed = (last[5] ** 2 + last[6] ** 2) ** 0.5
    print('[guided-distance-stall] %d rows; last east_m=%s speed=%s' % (len(track), last[4] if last else None, speed), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
