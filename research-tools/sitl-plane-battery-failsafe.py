"""Plane counterpart to sitl-copter-battery-failsafe.py. AP_BattMonitor's low-voltage failsafe was only confirmed on Copter so far (RTL, FS_LOW_ACT=2);
Plane::handle_battery_failsafe (ArduPlane/events.cpp) uses a different action enum (FS_LOW_ACT=1 is Failsafe_Action_RTL for Plane) and a fixed-wing cruise,
not a hover, so this is a genuinely different code path worth testing on its own rather than assumed from the Copter result.

Takes off via a real AUTO mission (matching the working pattern from sitl-plane-advanced-failsafe-terminate2.py - GUIDED+NAV_TAKEOFF does not climb a Plane),
reaches cruise altitude, sets BATT_LOW_VOLT just below SITL's default resting voltage and BATT_FS_LOW_ACT=1 (RTL), then drops SIM_BATT_VOLTAGE well below
that threshold and watches for the "Battery Failsafe" message, the mode switching to RTL, and the heading/track actually turning back toward home. Simulator
only.

    python3 sitl-plane-battery-failsafe.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
import csv
import math
import os
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link, mission, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(HOME[0]))
WORK = os.path.expanduser('~/cg-plane-battery-failsafe')
BIN = os.path.join(TREE, 'build/sitl/bin/arduplane')
TABLE = 'plane'
CRUISE_ALT_M = 60.0


def route():
    a = (HOME[0] + 400.0 / M_LAT, HOME[1])
    b = (a[0], a[1] + 400.0 / M_LON)
    c = (HOME[0], a[1])
    return [mission.Item(0, 0, 16, 0, 1, 0.0, 0.0, 0.0, 0.0, HOME[0], HOME[1], HOME[2]),
            mission.Item(1, 3, 22, 1, 1, 15.0, 0.0, 0.0, 0.0, 0.0, 0.0, CRUISE_ALT_M),
            mission.Item(2, 3, 16, 0, 1, 0.0, 0.0, 0.0, 0.0, a[0], a[1], CRUISE_ALT_M),
            mission.Item(3, 3, 16, 0, 1, 0.0, 0.0, 0.0, 0.0, b[0], b[1], CRUISE_ALT_M),
            mission.Item(4, 3, 17, 0, 1, 0.0, 0.0, 0.0, 0.0, c[0], c[1], CRUISE_ALT_M)]  # loiter unlimited, holds cruise until the failsafe takes over


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arduplane'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    notes, track = [], []
    proc = subprocess.Popen([BIN, '-w', '--model', 'plane', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME],
                            cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        time.sleep(30)
        base = link.read_params(conn)
        rest_v = base.get('SIM_BATT_VOLTAGE')
        notes.append('SIM_BATT_VOLTAGE default (resting) = %s' % rest_v)
        low_volt = round(rest_v - 0.5, 2) if rest_v else 11.5
        drop_volt = round(rest_v - 3.0, 2) if rest_v else 9.0
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 33, 200000, 0, 0, 0, 0, 0)  # GLOBAL_POSITION_INT 5Hz

        up = mission.upload(conn, route())
        notes.append('mission upload ack %s' % up)
        flight.set_mode(conn, 'MANUAL', table=TABLE)
        armed = flight.arm(conn, timeout=150.0)
        notes.append('arm: %s' % armed.detail)
        auto = flight.set_mode(conn, 'AUTO', table=TABLE)
        retry = time.time() + 60.0
        while not auto.ok and time.time() < retry:
            time.sleep(3)
            auto = flight.set_mode(conn, 'AUTO', table=TABLE)
        notes.append('AUTO: %s' % auto.detail)

        begin, reached = time.time(), False
        while time.time() - begin < 90.0:
            msg = conn.recv_match(type=['GLOBAL_POSITION_INT', 'STATUSTEXT'], blocking=True, timeout=1)
            if msg is None:
                continue
            if msg.get_type() == 'STATUSTEXT':
                notes.append('(climb) vehicle: %s' % msg.text)
            elif msg.get_type() == 'GLOBAL_POSITION_INT' and msg.relative_alt / 1000.0 >= CRUISE_ALT_M - 5.0:
                reached = True
                break
        notes.append('reached cruise altitude: %s, after %.0f s' % (reached, time.time() - begin))
        time.sleep(10.0)  # settle onto the loiter leg before injecting the fault

        bad2 = [r.name for r in params.write(conn, [
            params.Change('BATT_LOW_VOLT', base.get('BATT_LOW_VOLT'), low_volt),
            params.Change('BATT_FS_LOW_ACT', base.get('BATT_FS_LOW_ACT'), 1.0),
        ]) if not r.ok]
        notes.append('BATT_LOW_VOLT -> %s, BATT_FS_LOW_ACT -> 1 (RTL) (rejected %s)' % (low_volt, bad2))

        t0 = time.time()
        bad3 = [r.name for r in params.write(conn, [params.Change('SIM_BATT_VOLTAGE', rest_v, drop_volt)]) if not r.ok]
        notes.append('t=%5.1f SIM_BATT_VOLTAGE -> %s (rejected %s)' % (time.time() - t0, drop_volt, bad3))

        while time.time() - t0 < 60.0:
            msg = conn.recv_match(type=['GLOBAL_POSITION_INT', 'STATUSTEXT', 'HEARTBEAT'], blocking=True, timeout=1)
            if msg is None:
                continue
            t = time.time() - t0
            kind = msg.get_type()
            if kind == 'STATUSTEXT':
                notes.append('t=%5.1f vehicle: %s' % (t, msg.text))
            elif kind == 'GLOBAL_POSITION_INT':
                track.append([round(t, 1), msg.lat / 1e7, msg.lon / 1e7, msg.relative_alt / 1000.0])
            elif kind == 'HEARTBEAT' and msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                notes.append('t=%5.1f armed=%s custom_mode=%s' % (t, flight.is_armed(msg), msg.custom_mode))
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arduplane'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    with open(os.path.join(OUT, 'plane-battery-failsafe-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    with open(os.path.join(OUT, 'plane-battery-failsafe-track.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['seconds', 'lat', 'lon', 'relative_alt_m'])
        w.writerows(track)
    print('[plane-battery-failsafe] %d track rows; last 5: %s' % (len(track), track[-5:]), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
