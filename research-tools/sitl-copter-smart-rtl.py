"""First direct test of AP_SmartRTL (previously only autotest-name-matched, ap-lib:AP_SmartRTL - one autotest scenario did not pass there). SMART_RTL mode is meant
to retrace the path flown rather than cut straight home. This flies a clear L-shaped path in GUIDED (60m north, then 60m east, via SET_POSITION_TARGET_LOCAL_NED
position-only targets), switches to SMART_RTL, and records the full return track: if it genuinely retraces, the return path should pass back through roughly the
L's corner before heading south to home, not cut a single diagonal line straight home.

    python3 sitl-copter-smart-rtl.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
import csv
import math
import os
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link  # noqa: E402
from pymavlink import mavutil  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
WORK = os.path.expanduser('~/cg-copter-smart-rtl')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
TYPE_MASK_POSITION_ONLY = 0b0000111111111000
ALT_M = 20.0


def goto_local(conn, north_m, east_m, alt_m, timeout=60.0, tol_m=4.0):
    begin = time.time()
    last_pos = None
    while time.time() - begin < timeout:
        conn.mav.set_position_target_local_ned_send(0, conn.target_system, conn.target_component,
                                                      mavutil.mavlink.MAV_FRAME_LOCAL_NED, TYPE_MASK_POSITION_ONLY,
                                                      north_m, east_m, -alt_m, 0, 0, 0, 0, 0, 0, 0, 0)
        msg = conn.recv_match(type='LOCAL_POSITION_NED', blocking=True, timeout=0.5)
        if msg is None:
            continue
        last_pos = (msg.x, msg.y, msg.z)
        if math.hypot(msg.x - north_m, msg.y - east_m) <= tol_m:
            return True, last_pos
    return False, last_pos


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arducopter'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    notes, track = [], []
    proc = subprocess.Popen([BIN, '-w', '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                            stdout=open(os.path.join(WORK, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        time.sleep(20)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 32, 100000, 0, 0, 0, 0, 0)  # LOCAL_POSITION_NED at 10 Hz

        flight.set_mode(conn, 'GUIDED', table='copter')
        armed = flight.arm(conn, timeout=120.0)
        notes.append('arm: %s' % armed.detail)
        if armed.ok:
            conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, ALT_M)
            conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
            time.sleep(25.0)

            ok1, pos1 = goto_local(conn, 60.0, 0.0, ALT_M)
            notes.append('leg 1 (60m north) reached=%s at %s' % (ok1, pos1))
            ok2, pos2 = goto_local(conn, 60.0, 60.0, ALT_M)
            notes.append('leg 2 (60m north, 60m east) reached=%s at %s' % (ok2, pos2))

            srtl = flight.set_mode(conn, 'SMART_RTL', table='copter')
            notes.append('SMART_RTL: %s' % srtl.detail)

            t0 = time.time()
            while time.time() - t0 < 90.0:
                msg = conn.recv_match(type=['LOCAL_POSITION_NED', 'STATUSTEXT', 'HEARTBEAT'], blocking=True, timeout=1)
                if msg is None:
                    continue
                t = time.time() - t0
                kind = msg.get_type()
                if kind == 'STATUSTEXT':
                    notes.append('t=%5.1f vehicle: %s' % (t, msg.text))
                elif kind == 'LOCAL_POSITION_NED':
                    track.append([round(t, 1), round(msg.x, 1), round(msg.y, 1), round(-msg.z, 1)])
                elif kind == 'HEARTBEAT' and msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                    if not flight.is_armed(msg) and t > 5:
                        notes.append('t=%5.1f disarmed, stopping watch' % t)
                        break
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    with open(os.path.join(OUT, 'smart-rtl-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    with open(os.path.join(OUT, 'smart-rtl-track.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['seconds', 'north_m', 'east_m', 'alt_m'])
        w.writerows(track)
    print('[smart-rtl] %d track rows; last 5: %s' % (len(track), track[-5:]), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
