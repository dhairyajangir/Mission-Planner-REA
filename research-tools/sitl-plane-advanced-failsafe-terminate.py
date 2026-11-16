"""First direct test of AP_AdvancedFailsafe (previously only autotest-name-matched). AFS_ENABLE is an AP_PARAM_FLAG_ENABLE parameter (two-stage reboot); AFS_TERM_ACTION=42
(TERMINATE_ACTION_TERMINATE) selects the real "aerodynamic termination" action - the comment in should_crash_vehicle() says this is the only way should_crash_vehicle() can
ever return true. Flies a plain Plane into GUIDED cruise, then sends MAV_CMD_DO_FLIGHTTERMINATION (param1=1) - the same GCS-commanded path a ground station uses to force
termination - and watches AP_AdvancedFailsafe_Plane::terminate_vehicle() do exactly what its own source says: aileron/rudder/elevator slammed to SERVO_MAX, throttle forced
to MIN, then an immediate disarm (AP_Arming::Method::AFS). Simulator only - this is ArduPilot's own designed-in self-destruct mechanism for runaway aircraft, used here
exactly as intended, never on real hardware.

    python3 sitl-plane-advanced-failsafe-terminate.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
import csv
import os
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
WORK = os.path.expanduser('~/cg-plane-afs-terminate')
BIN = os.path.join(TREE, 'build/sitl/bin/arduplane')
TABLE = 'plane'
MAV_CMD_DO_FLIGHTTERMINATION = 185


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
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 36, 200000, 0, 0, 0, 0, 0)  # SERVO_OUTPUT_RAW

        guided = flight.set_mode(conn, 'GUIDED', table=TABLE)
        retry = time.time() + 60.0
        while not guided.ok and time.time() < retry:
            time.sleep(3)
            guided = flight.set_mode(conn, 'GUIDED', table=TABLE)
        notes.append('GUIDED (pre-arm): %s' % guided.detail)
        armed = flight.arm(conn, timeout=150.0)
        notes.append('arm: %s' % armed.detail)
        if armed.ok and guided.ok:
            conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, 60.0)
            begin, reached = time.time(), False
            while time.time() - begin < 60.0:
                msg = conn.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=1)
                if msg and msg.relative_alt / 1000.0 >= 55.0:
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
    with open(os.path.join(OUT, 'afs-terminate-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    with open(os.path.join(OUT, 'afs-terminate-track.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['seconds', 'relative_alt_m', 'vz_ms'])
        w.writerows(track)
    print('[afs-terminate] %d track rows; last 3: %s' % (len(track), track[-3:]), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
