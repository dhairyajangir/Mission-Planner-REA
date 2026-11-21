"""Closes the second loose end named in sitl-copter-battery-failsafe.py's limits: the capacity-based trigger (BATT_LOW_MAH), as opposed to the voltage trigger.
Reading AP_BattMonitor_Backend::update_failsafes (libraries/AP_BattMonitor/AP_BattMonitor_Backend.cpp) predicts a difference: the voltage paths start a timer and only
fire after BATT_LOW_TIMER seconds, but the capacity paths return Failsafe::Low/Critical as soon as (BATT_CAPACITY - consumed_mah) < BATT_LOW_MAH, with no timer.

Flies 60m north in GUIDED, reads BATT_CAPACITY and the live consumed mAh from BATTERY_STATUS, sets BATT_LOW_MAH so it is crossed after a further ~30 mAh of consumption
(BATT_LOW_VOLT is left alone - SIM_BATT_VOLTAGE is never touched), BATT_FS_LOW_ACT=2 (RTL), then records consumed mAh at 2 Hz and the time of the failsafe notice so the
delay between crossing the threshold and the notice can be read off directly. Simulator only.

    python3 sitl-copter-battery-failsafe-capacity.py <ardupilot tree> <out dir> <custom-gcs dir>
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
WORK = os.path.expanduser('~/cg-copter-battery-failsafe-capacity')
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
        capacity = base.get('BATT_CAPACITY')
        notes.append('BATT_CAPACITY=%s BATT_LOW_MAH=%s BATT_LOW_VOLT=%s' % (capacity, base.get('BATT_LOW_MAH'), base.get('BATT_LOW_VOLT')))
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 147, 500000, 0, 0, 0, 0, 0)  # BATTERY_STATUS at 2 Hz

        flight.set_mode(conn, 'GUIDED', table='copter')
        armed = flight.arm(conn, timeout=120.0)
        notes.append('arm: %s' % armed.detail)
        if armed.ok:
            conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, ALT_M)
            conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
            time.sleep(25.0)

            ok1, pos1 = goto_local(conn, 60.0, 0.0, ALT_M)
            notes.append('outbound leg (60m north) reached=%s at %s' % (ok1, pos1))

            bs = conn.recv_match(type='BATTERY_STATUS', blocking=True, timeout=5)
            consumed_now = bs.current_consumed if bs else None
            notes.append('consumed now = %s mAh' % consumed_now)
            low_mah = round(capacity - consumed_now - 30.0) if (capacity and consumed_now is not None) else 3000
            threshold_consumed = capacity - low_mah if capacity else None
            bad = [r.name for r in params.write(conn, [
                params.Change('BATT_LOW_MAH', base.get('BATT_LOW_MAH'), float(low_mah)),
                params.Change('BATT_FS_LOW_ACT', base.get('BATT_FS_LOW_ACT'), 2.0),
            ]) if not r.ok]
            notes.append('BATT_LOW_MAH -> %s (fires once consumed > %s mAh), BATT_FS_LOW_ACT -> 2 (RTL) (rejected %s)' % (low_mah, threshold_consumed, bad))
            t0 = time.time()
            crossed_at = None

            while time.time() - t0 < 90.0:
                msg = conn.recv_match(type=['LOCAL_POSITION_NED', 'STATUSTEXT', 'HEARTBEAT', 'BATTERY_STATUS'], blocking=True, timeout=1)
                if msg is None:
                    continue
                t = time.time() - t0
                kind = msg.get_type()
                if kind == 'BATTERY_STATUS':
                    notes.append('t=%5.1f consumed=%s mAh' % (t, msg.current_consumed))
                    if crossed_at is None and threshold_consumed is not None and msg.current_consumed > threshold_consumed:
                        crossed_at = t
                        notes.append('t=%5.1f *** consumed crossed the BATT_LOW_MAH threshold (%s mAh)' % (t, threshold_consumed))
                elif kind == 'STATUSTEXT':
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
    with open(os.path.join(OUT, 'battery-failsafe-capacity-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    with open(os.path.join(OUT, 'battery-failsafe-capacity-track.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['seconds', 'north_m', 'east_m', 'alt_m'])
        w.writerows(track)
    print('[battery-failsafe-capacity] %d track rows; last 5: %s' % (len(track), track[-5:]), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
