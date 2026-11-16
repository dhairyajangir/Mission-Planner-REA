"""First direct test of AP_Mount (previously only autotest-name-matched, ap-lib:AP_Mount). MNT1_TYPE=1 (Servo backend, the simplest - plain SERVO_FUNCTION outputs, no
simulated gimbal protocol) is an AP_PARAM_FLAG_ENABLE parameter (two-stage reboot). SERVO9_FUNCTION=7 (k_mount_tilt) and SERVO10_FUNCTION=6 (k_mount_pan) assign two
unused channels. Disarmed, on the ground - a mount command needs no flight at all. Sends MAV_CMD_DO_MOUNT_CONTROL (205) via COMMAND_INT with
MAV_MOUNT_MODE_MAVLINK_TARGETING (packet.z=2, param1=pitch deg, param2=roll deg, param3=yaw deg per AP_Mount_Backend::handle_command_do_mount_control) at three
different pitch/yaw targets, reading back SERVO_OUTPUT_RAW for channels 9 and 10 each time to confirm the outputs actually move, and move proportionally (not just once).

    python3 sitl-copter-mount-servo.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
import json
import os
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import link, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
WORK = os.path.expanduser('~/cg-copter-mount-servo')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
MAV_MOUNT_MODE_MAVLINK_TARGETING = 2


def read_servo9_10(conn):
    msg = conn.recv_match(type='SERVO_OUTPUT_RAW', blocking=True, timeout=5)
    return (msg.servo9_raw, msg.servo10_raw) if msg else (None, None)


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arducopter'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    notes, readings = [], []
    proc = subprocess.Popen([BIN, '-w', '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                            stdout=open(os.path.join(WORK, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        time.sleep(20)
        base = link.read_params(conn)
        want = {'MNT1_TYPE': 1.0, 'SERVO9_FUNCTION': 7.0, 'SERVO10_FUNCTION': 6.0}
        bad = [r.name for r in params.write(conn, [params.Change(n, base.get(n), v) for n, v in want.items()]) if not r.ok]
        notes.append('set %s; rejected %s; restarting under the new setting' % (want, bad))
        time.sleep(2)
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
        proc = subprocess.Popen([BIN, '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                                stdout=open(os.path.join(WORK, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)
        conn, _ = link.connect(5760, timeout=180.0)
        time.sleep(20)
        after = link.read_params(conn)
        notes.append('after restart: MNT1_TYPE=%s SERVO9_FUNCTION=%s SERVO10_FUNCTION=%s' %
                      (after.get('MNT1_TYPE'), after.get('SERVO9_FUNCTION'), after.get('SERVO10_FUNCTION')))
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 36, 200000, 0, 0, 0, 0, 0)  # SERVO_OUTPUT_RAW at 5 Hz

        neutral = read_servo9_10(conn)
        notes.append('servo9(tilt)/servo10(pan) before any mount command: %s' % (neutral,))

        for pitch, yaw in [(-45.0, 90.0), (20.0, -90.0), (0.0, 0.0)]:
            conn.mav.command_int_send(conn.target_system, conn.target_component, 0, 205, 0, 0, pitch, 0.0, yaw, 0.0, 0, 0, MAV_MOUNT_MODE_MAVLINK_TARGETING)
            ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
            time.sleep(2)
            s9, s10 = read_servo9_10(conn)
            notes.append('pitch=%.0f yaw=%.0f ack=%s -> servo9(tilt)=%s servo10(pan)=%s' %
                         (pitch, yaw, None if ack is None else ack.result, s9, s10))
            readings.append({'pitch': pitch, 'yaw': yaw, 'servo9_tilt': s9, 'servo10_pan': s10})
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        try:
            proc.wait(60)
        except Exception:
            proc.kill()
    with open(os.path.join(OUT, 'mount-servo-result.json'), 'w') as f:
        json.dump({'notes': notes, 'readings': readings}, f, indent=1)
    print('[mount-servo] %s' % readings, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
