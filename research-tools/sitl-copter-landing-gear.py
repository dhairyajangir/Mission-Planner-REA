"""First direct test of AP_LandingGear (previously only gdb reachability, ap-lib:AP_LandingGear - never a functional deploy/retract test). LGR_ENABLE is an
AP_PARAM_FLAG_ENABLE parameter (two-stage reboot); SERVO9_FUNCTION=29 (k_landing_gear_control) assigns an unused channel. The backend drives this channel to its
full SRV_Channel::Limit::MAX (deploy) or MIN (retract) - a limit-switch move, not a proportional one, unlike the mount/winch servos tested elsewhere in this
project. Disarmed, on the ground. Sends MAV_CMD_AIRFRAME_CONFIGURATION (2520) via COMMAND_INT (param2: 0=deploy, 1=retract per
GCS_MAVLINK::handle_command_airframe_configuration), reading SERVO_OUTPUT_RAW channel 9 after each.

    python3 sitl-copter-landing-gear.py <ardupilot tree> <out dir> <custom-gcs dir>
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
WORK = os.path.expanduser('~/cg-copter-landing-gear')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
MAV_CMD_AIRFRAME_CONFIGURATION = 2520


def read_servo9(conn):
    msg = conn.recv_match(type='SERVO_OUTPUT_RAW', blocking=True, timeout=5)
    return msg.servo9_raw if msg else None


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
        want = {'LGR_ENABLE': 1.0, 'SERVO9_FUNCTION': 29.0}
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
        notes.append('after restart: LGR_ENABLE=%s SERVO9_FUNCTION=%s' % (after.get('LGR_ENABLE'), after.get('SERVO9_FUNCTION')))
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 36, 200000, 0, 0, 0, 0, 0)

        s9 = read_servo9(conn)
        notes.append('servo9(landing gear) before any command: %s' % s9)
        readings.append({'phase': 'before', 'servo9': s9})

        for label, param2 in [('retract', 1.0), ('deploy', 0.0), ('retract', 1.0)]:
            conn.mav.command_int_send(conn.target_system, conn.target_component, 0, MAV_CMD_AIRFRAME_CONFIGURATION, 0, 0, 0.0, param2, 0.0, 0.0, 0, 0, 0)
            ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
            time.sleep(1.0)
            s9 = read_servo9(conn)
            notes.append('%s (param2=%.0f) ack=%s -> servo9=%s' % (label, param2, None if ack is None else ack.result, s9))
            readings.append({'phase': label, 'servo9': s9})
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        try:
            proc.wait(60)
        except Exception:
            proc.kill()
    with open(os.path.join(OUT, 'landing-gear-result.json'), 'w') as f:
        json.dump({'notes': notes, 'readings': readings}, f, indent=1)
    print('[landing-gear] %s' % readings, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
