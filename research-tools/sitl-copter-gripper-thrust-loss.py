"""Connects two things already found separately in this project: the single motor failure test (Copter::thrust_loss_check fires "Potential Thrust Loss" 1.8s after
ground contact from 30m - too late) and AP_Gripper (previously only autotest-name-matched). ArduCopter/crash_check.cpp's thrust_loss_check() calls gripper.release()
in the exact same branch as the "Potential Thrust Loss" message, gated by FLIGHT_OPTIONS bit 2 (RELEASE_GRIPPER_ON_THRUST_LOSS, value 4) - so the gripper-release
safety action necessarily inherits the detector's own timing. This confirms that empirically: GRIP_ENABLE=1 (two-stage reboot), GRIP_TYPE=1 (servo),
SERVO9_FUNCTION=28 (k_gripper), default GRIP_GRAB=1900/GRIP_RELEASE=1100 PWM, FLIGHT_OPTIONS=4. Same 30m motor-failure recipe as before: GUIDED takeoff, fail motor 1,
watch SERVO_OUTPUT_RAW channel 9 (gripper) alongside the STATUSTEXT stream to see exactly when (if ever, before or after ground contact) it switches to the release
PWM.

    python3 sitl-copter-gripper-thrust-loss.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
import json
import os
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
TAKEOFF_ALT_M = 30.0
WORK = os.path.expanduser('~/cg-copter-gripper-thrust-loss')
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
        want = {'GRIP_ENABLE': 1.0, 'GRIP_TYPE': 1.0, 'SERVO9_FUNCTION': 28.0, 'FLIGHT_OPTIONS': 4.0}
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
        notes.append('after restart: GRIP_ENABLE=%s GRIP_TYPE=%s GRIP_GRAB=%s GRIP_RELEASE=%s FLIGHT_OPTIONS=%s SERVO9_FUNCTION=%s' %
                      (after.get('GRIP_ENABLE'), after.get('GRIP_TYPE'), after.get('GRIP_GRAB'), after.get('GRIP_RELEASE'),
                       after.get('FLIGHT_OPTIONS'), after.get('SERVO9_FUNCTION')))
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 33, 100000, 0, 0, 0, 0, 0)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 36, 200000, 0, 0, 0, 0, 0)  # SERVO_OUTPUT_RAW

        servo_functions = {ch: after.get('SERVO%d_FUNCTION' % ch) for ch in range(1, 9)}
        motor_channels = [ch for ch, fn in servo_functions.items() if fn == 33.0]
        fail_bit = float(1 << (motor_channels[0] - 1)) if motor_channels else 1.0

        flight.set_mode(conn, 'GUIDED', table='copter')
        armed = flight.arm(conn, timeout=120.0)
        notes.append('arm: %s' % armed.detail)
        if armed.ok:
            conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, TAKEOFF_ALT_M)
            ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
            notes.append('takeoff to %.0f m ack %s' % (TAKEOFF_ALT_M, None if ack is None else ack.result))
            time.sleep(max(25.0, TAKEOFF_ALT_M))
            g9 = conn.recv_match(type='SERVO_OUTPUT_RAW', blocking=True, timeout=5)
            notes.append('gripper servo9 before fault (should be GRAB pwm): %s' % (g9.servo9_raw if g9 else None))
            bad = [r.name for r in params.write(conn, [params.Change('SIM_ENGINE_FAIL', 0.0, fail_bit)]) if not r.ok]
            notes.append('SIM_ENGINE_FAIL -> %d (motor channel %s killed) (rejected %s)' % (fail_bit, motor_channels, bad))
            t0 = time.time()
            released_at = None
            while time.time() - t0 < 25.0:
                msg = conn.recv_match(type=['SERVO_OUTPUT_RAW', 'STATUSTEXT', 'HEARTBEAT'], blocking=True, timeout=1)
                if msg is None:
                    continue
                t = time.time() - t0
                kind = msg.get_type()
                if kind == 'STATUSTEXT':
                    notes.append('t=%5.1f vehicle: %s' % (t, msg.text))
                elif kind == 'SERVO_OUTPUT_RAW':
                    track.append([round(t, 1), msg.servo9_raw])
                    if released_at is None and msg.servo9_raw <= 1200:
                        released_at = t
                        notes.append('t=%5.1f gripper servo9 switched to release range (%d)' % (t, msg.servo9_raw))
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    with open(os.path.join(OUT, 'gripper-thrust-loss-result.json'), 'w') as f:
        json.dump({'notes': notes, 'track': track}, f, indent=1)
    print('[gripper-thrust-loss] %s' % notes[-5:], flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
