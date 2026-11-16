"""Closes the loose end named in sitl-copter-battery-failsafe.py's limits: only the low-battery/RTL path (BATT_LOW_VOLT, FS_LOW_ACT=2) was tried there.
This isolates the separate critical-battery path instead: BATT_LOW_VOLT is disabled (0) so only BATT_CRT_VOLT/BATT_FS_CRT_ACT can fire, and FS_CRT_ACT=1
is Land for Copter (Copter::handle_battery_failsafe, ArduCopter/events.cpp) - a different, more severe response than RTL, expected to descend in place
rather than fly home first.

Flies 60m north in GUIDED (so a later RTL-vs-Land distinction would be visible even though Land is not expected to fly anywhere), then sets
BATT_CRT_VOLT=12.1 and BATT_FS_CRT_ACT=1 with BATT_LOW_VOLT=0, drops SIM_BATT_VOLTAGE to 9.6, and watches for "Battery Failsafe", the mode switching to
LAND, and a controlled descent to the ground with auto-disarm. Simulator only.

    python3 sitl-copter-battery-failsafe-critical.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
import csv
import math
import os
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link, params  # noqa: E402
from pymavlink import mavutil  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
WORK = os.path.expanduser('~/cg-copter-battery-failsafe-critical')
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

        base = link.read_params(conn)
        rest_v = base.get('SIM_BATT_VOLTAGE')
        notes.append('SIM_BATT_VOLTAGE default (resting) = %s' % rest_v)

        flight.set_mode(conn, 'GUIDED', table='copter')
        armed = flight.arm(conn, timeout=120.0)
        notes.append('arm: %s' % armed.detail)
        if armed.ok:
            conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, ALT_M)
            conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
            time.sleep(25.0)

            ok1, pos1 = goto_local(conn, 60.0, 0.0, ALT_M)
            notes.append('outbound leg (60m north) reached=%s at %s' % (ok1, pos1))

            crt_volt = round(rest_v - 0.5, 2) if rest_v else 11.5
            drop_volt = round(rest_v - 3.0, 2) if rest_v else 9.0
            bad = [r.name for r in params.write(conn, [
                params.Change('BATT_LOW_VOLT', base.get('BATT_LOW_VOLT'), 0.0),
                params.Change('BATT_CRT_VOLT', base.get('BATT_CRT_VOLT'), crt_volt),
                params.Change('BATT_FS_CRT_ACT', base.get('BATT_FS_CRT_ACT'), 1.0),
            ]) if not r.ok]
            notes.append('BATT_LOW_VOLT -> 0 (disabled), BATT_CRT_VOLT -> %s, BATT_FS_CRT_ACT -> 1 (Land) (rejected %s)' % (crt_volt, bad))

            t0 = time.time()
            bad2 = [r.name for r in params.write(conn, [params.Change('SIM_BATT_VOLTAGE', rest_v, drop_volt)]) if not r.ok]
            notes.append('t=%5.1f SIM_BATT_VOLTAGE -> %s (rejected %s)' % (time.time() - t0, drop_volt, bad2))

            while time.time() - t0 < 60.0:
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
                    notes.append('t=%5.1f armed=%s custom_mode=%s' % (t, flight.is_armed(msg), msg.custom_mode))
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
    with open(os.path.join(OUT, 'battery-failsafe-critical-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    with open(os.path.join(OUT, 'battery-failsafe-critical-track.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['seconds', 'north_m', 'east_m', 'alt_m'])
        w.writerows(track)
    print('[battery-failsafe-critical] %d track rows; last 5: %s' % (len(track), track[-5:]), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
