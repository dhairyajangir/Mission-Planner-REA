"""Corrected follow-up to sitl-plane-advanced-failsafe-terminate.py, which confirmed AP_AdvancedFailsafe's termination mechanism but never got the aircraft airborne
(GUIDED+NAV_TAKEOFF does not produce a climb for Plane). This uses a real AUTO mission takeoff item instead (the same working pattern as run_plane.py's route()),
waits for the climb and the transit to the first waypoint, then sends MAV_CMD_DO_FLIGHTTERMINATION (185, param1=1) while genuinely cruising, to see the actual
fall/crash this safety system is designed to produce - not just the servo-override signature in isolation.

    python3 sitl-plane-advanced-failsafe-terminate2.py <ardupilot tree> <out dir> <custom-gcs dir>
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
WORK = os.path.expanduser('~/cg-plane-afs-terminate2')
BIN = os.path.join(TREE, 'build/sitl/bin/arduplane')
TABLE = 'plane'
MAV_CMD_DO_FLIGHTTERMINATION = 185
CRUISE_ALT_M = 60.0


def route():
    a = (HOME[0] + 300.0 / M_LAT, HOME[1])
    b = (a[0], a[1] + 300.0 / M_LON)
    return [mission.Item(0, 0, 16, 0, 1, 0.0, 0.0, 0.0, 0.0, HOME[0], HOME[1], HOME[2]),
            mission.Item(1, 3, 22, 1, 1, 15.0, 0.0, 0.0, 0.0, 0.0, 0.0, CRUISE_ALT_M),
            mission.Item(2, 3, 16, 0, 1, 0.0, 0.0, 0.0, 0.0, a[0], a[1], CRUISE_ALT_M),
            mission.Item(3, 3, 16, 0, 1, 0.0, 0.0, 0.0, 0.0, b[0], b[1], CRUISE_ALT_M)]


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
        want = {'AFS_ENABLE': 1.0, 'AFS_TERM_ACTION': 42.0}
        bad = [r.name for r in params.write(conn, [params.Change(n, base.get(n), v) for n, v in want.items()]) if not r.ok]
        notes.append('set %s; rejected %s; restarting under the new setting' % (want, bad))
        time.sleep(2)
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
        proc = subprocess.Popen([BIN, '--model', 'plane', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME],
                                cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)
        conn, _ = link.connect(5760, timeout=180.0)
        time.sleep(30)
        after = link.read_params(conn)
        notes.append('after restart: AFS_ENABLE=%s AFS_TERM_ACTION=%s' % (after.get('AFS_ENABLE'), after.get('AFS_TERM_ACTION')))
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 33, 200000, 0, 0, 0, 0, 0)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 36, 200000, 0, 0, 0, 0, 0)

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

        s_before = conn.recv_match(type='SERVO_OUTPUT_RAW', blocking=True, timeout=5)
        notes.append('SERVO_OUTPUT_RAW before termination: servo1(aileron)=%s servo2(elevator)=%s servo3(throttle)=%s servo4(rudder)=%s' %
                     ((s_before.servo1_raw, s_before.servo2_raw, s_before.servo3_raw, s_before.servo4_raw) if s_before else (None, None, None, None)))

        conn.mav.command_int_send(conn.target_system, conn.target_component, 0, MAV_CMD_DO_FLIGHTTERMINATION, 0, 0, 1.0, 0, 0, 0, 0, 0, 0)
        ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
        notes.append('DO_FLIGHTTERMINATION param1=1 ack=%s' % (None if ack is None else ack.result))

        t0 = time.time()
        s_after_logged = False
        while time.time() - t0 < 60.0:
            msg = conn.recv_match(type=['SERVO_OUTPUT_RAW', 'STATUSTEXT', 'HEARTBEAT', 'GLOBAL_POSITION_INT'], blocking=True, timeout=1)
            if msg is None:
                continue
            t = time.time() - t0
            kind = msg.get_type()
            if kind == 'STATUSTEXT':
                notes.append('t=%5.1f vehicle: %s' % (t, msg.text))
            elif kind == 'SERVO_OUTPUT_RAW' and not s_after_logged:
                notes.append('t=%5.1f SERVO_OUTPUT_RAW: servo1(aileron)=%s servo2(elevator)=%s servo3(throttle)=%s servo4(rudder)=%s' %
                             (t, msg.servo1_raw, msg.servo2_raw, msg.servo3_raw, msg.servo4_raw))
                s_after_logged = True
            elif kind == 'GLOBAL_POSITION_INT':
                track.append([round(t, 1), msg.relative_alt / 1000.0, msg.vz / 100.0])
            elif kind == 'HEARTBEAT' and msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                if not flight.is_armed(msg) and t > 1:
                    notes.append('t=%5.1f disarmed' % t)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arduplane'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    with open(os.path.join(OUT, 'afs-terminate2-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    with open(os.path.join(OUT, 'afs-terminate2-track.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['seconds', 'relative_alt_m', 'vz_ms'])
        w.writerows(track)
    print('[afs-terminate2] %d track rows; last 3: %s' % (len(track), track[-3:]), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
