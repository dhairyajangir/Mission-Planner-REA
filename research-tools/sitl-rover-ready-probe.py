"""Why did the custom-gcs rover motor test miss outputs? Simulator only (disposable ArduRover SITL in WSL).

The sweep (sitl-rover-frame-motor-sweep.py) waits 25 s after the heartbeat and every test moved the predicted outputs. custom-gcs waited for
HEARTBEAT system_status >= STANDBY and then ran for about 4 s before the first test; throttle left (skid) and throttle/steering (sailboat) did not move.
This probe starts the simulator, then every 5 s after the first heartbeat sends motor test 3 (throttle left) 40 percent for 1 s and prints the COMMAND_ACK
result, STATUSTEXT, heartbeat system_status and the maximum change of SERVO1..4 within 2 s. Output is plain text on stdout.

    python sitl-rover-ready-probe.py <ardupilot tree> <model> [seconds to probe, default 60]
"""
import os
import subprocess
import sys
import time

from pymavlink import mavutil

TREE, MODEL = sys.argv[1], sys.argv[2]
SPAN = float(sys.argv[3]) if len(sys.argv) > 3 else 60.0
WORK = os.path.expanduser('~/rover-ready/' + MODEL)


def main():
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardurover'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    proc = subprocess.Popen([os.path.join(TREE, 'build/sitl/bin/ardurover'), '-w', '--model', MODEL, '-I', '0', '-s', '1', '--home', '-35.363261,149.165230,584,0'],
                            cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    try:
        link = None
        end = time.time() + 60
        while time.time() < end and link is None:
            try:
                link = mavutil.mavlink_connection('tcp:127.0.0.1:5760', autoreconnect=False)
                link.wait_heartbeat(timeout=30)
            except Exception:
                link = None
                time.sleep(1)
        if link is None:
            print('no connection')
            return 1
        t0 = time.time()
        link.mav.command_long_send(link.target_system, link.target_component, mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0, 36, 50000, 0, 0, 0, 0, 0)
        status = None
        next_probe = 0.0
        base = None
        window = None
        while time.time() - t0 < SPAN:
            now = time.time() - t0
            if now >= next_probe and window is None:
                link.mav.command_long_send(link.target_system, link.target_component, mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST, 0, 3, 0, 40, 1, 0, 0, 0)
                print('t=%5.1f  sent motor test 3 (system_status=%s)' % (now, status))
                window = (now + 2.5, [])
                next_probe = now + 5.0
            msg = link.recv_match(blocking=True, timeout=0.1)
            if msg is None:
                continue
            kind = msg.get_type()
            if kind == 'HEARTBEAT' and msg.get_srcComponent() == 1:
                status = msg.system_status
            elif kind == 'COMMAND_ACK' and msg.command == mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST:
                print('t=%5.1f  ack result=%d' % (now, msg.result))
            elif kind == 'STATUSTEXT':
                print('t=%5.1f  text: %s' % (now, msg.text))
            elif kind == 'SERVO_OUTPUT_RAW' and window is not None:
                window[1].append([msg.servo1_raw, msg.servo2_raw, msg.servo3_raw, msg.servo4_raw])
            if window is not None and now >= window[0]:
                rows = window[1]
                spread = [max(r[i] for r in rows) - min(r[i] for r in rows) for i in range(4)] if rows else None
                print('t=%5.1f  servo1..4 spread over the window: %s' % (now, spread))
                window = None
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
    return 0


if __name__ == '__main__':
    sys.exit(main())
