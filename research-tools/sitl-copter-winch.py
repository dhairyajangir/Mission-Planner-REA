"""First direct test of AP_Winch (previously only autotest-name-matched). WINCH_TYPE=1 (PWM backend, AP_Winch_PWM.cpp - plain SRV_Channel output, no simulated winch
hardware), an AP_PARAM_FLAG_ENABLE parameter (two-stage reboot, prefix is WINCH_ not an abbreviation). SERVO9_FUNCTION=88 (k_winch) assigns an unused channel.
Disarmed, on the ground. Sends MAV_CMD_DO_WINCH (42600) via COMMAND_INT: action=2 (rate control, param4=rate) then action=0 (relax, AP_Winch_PWM::control_winch's
RELAXED branch sets raw PWM to 0 directly, bypassing its own acceleration-rate-limiting ramp), reading SERVO_OUTPUT_RAW channel 9 after each, with a short wait for
the rate-controlled case since the backend ramps toward the commanded rate rather than jumping to it.

    python3 sitl-copter-winch.py <ardupilot tree> <out dir> <custom-gcs dir>
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
WORK = os.path.expanduser('~/cg-copter-winch')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
MAV_CMD_DO_WINCH = 42600
WINCH_RELAXED, WINCH_RATE_CONTROL = 0, 2


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
        want = {'WINCH_TYPE': 1.0, 'SERVO9_FUNCTION': 88.0}
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
        notes.append('after restart: WINCH_TYPE=%s SERVO9_FUNCTION=%s' % (after.get('WINCH_TYPE'), after.get('SERVO9_FUNCTION')))
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 36, 200000, 0, 0, 0, 0, 0)

        s9 = read_servo9(conn)
        notes.append('servo9(winch) before any command: %s' % s9)
        readings.append({'phase': 'before', 'servo9': s9})

        conn.mav.command_int_send(conn.target_system, conn.target_component, 0, MAV_CMD_DO_WINCH, 0, 0, 0.0, float(WINCH_RATE_CONTROL), 0.0, 2.0, 0, 0, 0)
        ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
        time.sleep(3)  # the rate-limited ramp needs a moment to reach the commanded rate
        s9 = read_servo9(conn)
        notes.append('DO_WINCH rate=2.0 ack=%s -> servo9=%s (after 3s ramp)' % (None if ack is None else ack.result, s9))
        readings.append({'phase': 'rate_control_2.0', 'servo9': s9})

        conn.mav.command_int_send(conn.target_system, conn.target_component, 0, MAV_CMD_DO_WINCH, 0, 0, 0.0, float(WINCH_RELAXED), 0.0, 0.0, 0, 0, 0)
        ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
        time.sleep(0.5)
        s9 = read_servo9(conn)
        notes.append('DO_WINCH relax ack=%s -> servo9=%s' % (None if ack is None else ack.result, s9))
        readings.append({'phase': 'relax', 'servo9': s9})
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        try:
            proc.wait(60)
        except Exception:
            proc.kill()
    with open(os.path.join(OUT, 'winch-result.json'), 'w') as f:
        json.dump({'notes': notes, 'readings': readings}, f, indent=1)
    print('[winch] %s' % readings, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
