"""What does MAV_CMD_DO_MOTOR_TEST do on a Copter helicopter build? Simulator only (disposable arducopter-heli SITL in WSL).

Source (ArduCopter/motor_test.cpp, libraries/AP_Motors/AP_MotorsHeli.h): AP_MotorsHeli overrides _output_test_seq with an empty body ("disabled on heli, do nothing").
My first reading was that the Copter side would still accept the command and arm the motors; the run showed otherwise, the vehicle refuses it (see below). This probe
sends sequences 1 to 4 at 10 percent for 2 s, resending a rejected command for up to 60 s, and prints the COMMAND_ACK result, STATUSTEXT and, for each of the
SERVO_OUTPUT_RAW outputs 1 to 16, the outputs that changed by 20 us or more from the start of that step. Result (sitl-evidence/heli-motor-test-probe/): on heli,
heli-dual and heli-quad every sequence is answered with COMMAND_ACK result 4 (FAILED) and the text "Motor Test: Disabled on heli"; no output moves.

    python sitl-heli-motor-test-probe.py <ardupilot tree> <model, e.g. heli> [instance]
"""
import os
import subprocess
import sys
import time

from pymavlink import mavutil

TREE, MODEL = sys.argv[1], sys.argv[2]
WORK = os.path.expanduser('~/heli-probe/' + MODEL)


def drain(link, seconds, send=None, events=None):
    rows, end, last = [], time.time() + seconds, 0.0
    while time.time() < end:
        if send and time.time() - last >= 1.0:
            send()
            last = time.time()
        msg = link.recv_match(type=['SERVO_OUTPUT_RAW', 'COMMAND_ACK', 'STATUSTEXT'], blocking=True, timeout=0.1)
        if msg is None:
            continue
        kind = msg.get_type()
        if kind == 'SERVO_OUTPUT_RAW':
            rows.append([getattr(msg, 'servo%d_raw' % i, 0) for i in range(1, 17)])
        elif events is not None and kind == 'COMMAND_ACK' and msg.command == mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST:
            events.append('ack result=%d' % msg.result)
        elif events is not None and kind == 'STATUSTEXT':
            events.append('text: ' + msg.text)
    return rows


def main():
    subprocess.call(['pkill', '-f', 'build/sitl/bin/arducopter'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    proc = subprocess.Popen([os.path.join(TREE, 'build/sitl/bin/arducopter-heli'), '-w', '--model', MODEL, '-I', '0', '-s', '1', '--home', '-35.363261,149.165230,584,0'],
                            cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    try:
        link = None
        end = time.time() + 60
        while link is None and time.time() < end:
            try:
                link = mavutil.mavlink_connection('tcp:127.0.0.1:5760', autoreconnect=False)
                link.wait_heartbeat(timeout=30)
            except Exception:
                link = None
                time.sleep(1)
        if link is None:
            print('no connection')
            return 1
        link.mav.command_long_send(link.target_system, link.target_component, mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0, 36, 50000, 0, 0, 0, 0, 0)
        print('model %s: heartbeat type %d' % (MODEL, link.messages['HEARTBEAT'].type if 'HEARTBEAT' in link.messages else -1))
        drain(link, 20)
        base = (drain(link, 3) or [[0] * 16])[-1]
        for seq in range(1, 5):
            send = lambda s=seq: link.mav.command_long_send(link.target_system, link.target_component, mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST, 0, s, 0, 10, 2, 0, 0, 0)
            events = []
            deadline = time.time() + 60
            rows = []
            while True:
                events.clear()
                rows = drain(link, 3.0, send, events)
                accepted = any(e == 'ack result=0' for e in events)
                if accepted or time.time() >= deadline:
                    break
                time.sleep(1)
            spread = {i + 1: max(abs(r[i] - base[i]) for r in rows) for i in range(16)} if rows else {}
            moved = {k: v for k, v in spread.items() if v >= 20}
            print('sequence %d: accepted=%s events=%s outputs that changed by 20 us or more: %s' % (seq, accepted, sorted(set(events)), moved or 'none'))
            drain(link, 3)
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
    return 0


if __name__ == '__main__':
    sys.exit(main())
