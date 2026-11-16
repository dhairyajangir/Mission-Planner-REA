"""Fault injection follow-up to the single motor failure test (sitl-copter-motor-failure.py), which found Copter::thrust_loss_check firing too late (1.8s after ground
contact from 30m) or not at all (100m fall). ArduCopter has a completely separate automatic safety response never tried anywhere in this project: Copter::parachute_check()
(ArduCopter/crash_check.cpp) auto-deploys AP_Parachute if either (a) attitude error exceeds 30 degrees continuously for 1s, or (b) AP_Parachute::check_sink_rate() sees the
sink rate over CHUTE_CRT_SINK continuously for 1s - CHUTE_CRT_SINK defaults to 0 (disabled), so this sets it to 10 m/s to actually exercise that path. CHUTE_ENABLED is an
AP_PARAM_FLAG_ENABLE parameter (two-stage reboot); CHUTE_TYPE=10 (servo) with SERVO9_FUNCTION=27 (k_parachute_release) avoids needing a simulated relay. Same recipe as the
motor-failure test otherwise: GUIDED takeoff to 30m, kill motor 1, watch whether "Parachute: Released" arrives before or after ground contact this time.

    python3 sitl-copter-parachute-motor-failure.py <ardupilot tree> <out dir> <custom-gcs dir> [takeoff_alt_m]
"""
import csv
import os
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
TAKEOFF_ALT_M = float(sys.argv[4]) if len(sys.argv) > 4 else 30.0
sys.path.insert(0, GCS)
from customgcs import flight, link, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
WORK = os.path.expanduser('~/cg-copter-parachute-motor-failure')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arducopter'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    notes, track = [], []
    proc = subprocess.Popen([BIN, '-w', '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME],
                            cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        time.sleep(20)
        base = link.read_params(conn)
        want = {'CHUTE_ENABLED': 1.0, 'CHUTE_TYPE': 10.0, 'SERVO9_FUNCTION': 27.0, 'CHUTE_CRT_SINK': 10.0, 'CHUTE_ALT_MIN': 0.0}
        bad = [r.name for r in params.write(conn, [params.Change(n, base.get(n), v) for n, v in want.items()]) if not r.ok]
        notes.append('set %s; rejected %s; restarting under the new setting' % (want, bad))
        time.sleep(2)
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
        proc = subprocess.Popen([BIN, '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME],
                                cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)
        conn, _ = link.connect(5760, timeout=180.0)
        time.sleep(20)
        after = link.read_params(conn)
        notes.append('after restart: CHUTE_ENABLED=%s CHUTE_TYPE=%s CHUTE_CRT_SINK=%s SERVO9_FUNCTION=%s' %
                      (after.get('CHUTE_ENABLED'), after.get('CHUTE_TYPE'), after.get('CHUTE_CRT_SINK'), after.get('SERVO9_FUNCTION')))
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 33, 100000, 0, 0, 0, 0, 0)

        servo_functions = {ch: after.get('SERVO%d_FUNCTION' % ch) for ch in range(1, 9)}
        motor_channels = [ch for ch, fn in servo_functions.items() if fn == 33.0]
        notes.append('SERVOx_FUNCTION: %s; k_motor1 (33) on channel(s): %s' % (servo_functions, motor_channels))
        fail_bit = float(1 << (motor_channels[0] - 1)) if motor_channels else 1.0

        flight.set_mode(conn, 'GUIDED', table='copter')
        armed = flight.arm(conn, timeout=120.0)
        notes.append('arm: %s' % armed.detail)
        if armed.ok:
            conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, TAKEOFF_ALT_M)
            ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
            notes.append('takeoff to %.0f m ack %s' % (TAKEOFF_ALT_M, None if ack is None else ack.result))
            time.sleep(max(25.0, TAKEOFF_ALT_M))
            bad = [r.name for r in params.write(conn, [params.Change('SIM_ENGINE_FAIL', 0.0, fail_bit)]) if not r.ok]
            notes.append('SIM_ENGINE_FAIL -> %d (motor channel %s killed) (rejected %s)' % (fail_bit, motor_channels, bad))
            t0 = time.time()
            while time.time() - t0 < 25.0:
                msg = conn.recv_match(type=['GLOBAL_POSITION_INT', 'STATUSTEXT', 'HEARTBEAT'], blocking=True, timeout=1)
                if msg is None:
                    continue
                t = time.time() - t0
                kind = msg.get_type()
                if kind == 'STATUSTEXT':
                    notes.append('t=%5.1f vehicle: %s' % (t, msg.text))
                elif kind == 'GLOBAL_POSITION_INT':
                    track.append([round(t, 1), msg.relative_alt / 1000.0, msg.vz / 100.0])
                elif kind == 'HEARTBEAT' and msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                    notes.append('t=%5.1f armed=%s' % (t, flight.is_armed(msg)))
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    with open(os.path.join(OUT, 'copter-parachute-motor-failure-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    with open(os.path.join(OUT, 'copter-parachute-motor-failure-track.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['seconds', 'relative_alt_m', 'vz_ms'])
        w.writerows(track)
    last = track[-1] if track else None
    print('[copter-parachute-motor-failure] %d rows; last alt=%s vz=%s' % (len(track), last[1] if last else None, last[2] if last else None), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
