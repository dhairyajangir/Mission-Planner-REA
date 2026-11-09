"""Motor test across the ArduRover simulator frames on disposable Rover SITLs (WSL, pymavlink). Simulator only.

ArduRover's MAV_CMD_DO_MOTOR_TEST (Rover/motor_test.cpp, AP_MotorsUGV::output_test_pct) takes param1 = 1 throttle, 2 steering, 3 throttle left, 4 throttle right,
5 main sail, and drives every output whose SERVOn_FUNCTION is the matching function: throttle (70) or motor1 (33); steering (26) or motor2 (34); throttle left (73) or
motor3 (35); throttle right (74) or motor4 (36); main sail sheet (89), wing sail elevator (128) or mast rotation (137). It arms the vehicle itself and switches off the
GCS, throttle and crash failsafes.

For each frame this script starts the simulator (--model <frame>), reads SERVO1_FUNCTION to SERVO16_FUNCTION from the vehicle, sends the test for param1 = 1..5
(50 percent, 2 s) and records SERVO_OUTPUT_RAW, and compares the outputs that moved with the outputs the vehicle's own SERVOn_FUNCTION values predict. The prediction
is made from the same vehicle's parameters, not from a table I wrote.

    python sitl-rover-frame-motor-sweep.py <ardupilot tree> <out dir> [frame ...]
"""
import csv
import os
import subprocess
import sys
import time

from pymavlink import mavutil

TREE, OUT = sys.argv[1], sys.argv[2]
FRAMES = sys.argv[3:] or ['rover', 'rover-skid', 'rover-omni3mecanum', 'rover-vectored', 'balancebot', 'motorboat', 'motorboat-skid', 'sailboat', 'sailboat-motor']
INSTANCE = int(os.environ.get('SWEEP_INSTANCE', '0'))
PORT = 5760 + 10 * INSTANCE
FUNCS = {1: (70, 33), 2: (26, 34), 3: (73, 35), 4: (74, 36), 5: (89, 128, 137)}
NAMES = {1: 'throttle', 2: 'steering', 3: 'throttle left', 4: 'throttle right', 5: 'main sail'}


def start(frame, work):
    os.makedirs(work, exist_ok=True)
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardurover'])
    time.sleep(1)
    return subprocess.Popen([os.path.join(TREE, 'build/sitl/bin/ardurover'), '-w', '--model', frame, '-I', str(INSTANCE), '-s', '1', '--home', '-35.363261,149.165230,584,0'],
                            cwd=work, stdout=open(os.path.join(work, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)


def connect():
    t0 = time.time()
    while time.time() - t0 < 60:
        try:
            m = mavutil.mavlink_connection('tcp:127.0.0.1:%d' % PORT, autoreconnect=False)
            m.wait_heartbeat(timeout=30)
            return m
        except Exception:
            time.sleep(1)
    return None


def get_param(m, name):
    for _ in range(5):
        m.mav.param_request_read_send(m.target_system, m.target_component, name.encode(), -1)
        r = m.recv_match(type='PARAM_VALUE', blocking=True, timeout=3)
        if r is not None and r.param_id.rstrip('\x00') == name:
            return int(r.param_value)
    return None


def drain(m, secs, rows, texts):
    end = time.time() + secs
    while time.time() < end:
        msg = m.recv_match(type=['SERVO_OUTPUT_RAW', 'STATUSTEXT'], blocking=True, timeout=0.1)
        if msg is None:
            continue
        if msg.get_type() == 'SERVO_OUTPUT_RAW':
            rows.append([time.time()] + [getattr(msg, 'servo%d_raw' % i, 0) for i in range(1, 17)])
        else:
            texts.append(msg.text)


def one_frame(frame, work):
    subprocess.call(['rm', '-rf', work])
    proc = start(frame, work)
    summary, per = {'frame': frame}, []
    try:
        m = connect()
        if m is None:
            summary['status'] = 'no connection'
            return summary, per
        functions = [get_param(m, 'SERVO%d_FUNCTION' % i) for i in range(1, 17)]
        summary['servo_functions_1_to_16'] = ' '.join(str(f) for f in functions)
        m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0, 36, 50000, 0, 0, 0, 0, 0)
        rows, texts = [], []
        drain(m, 25, rows, texts)                           # let the vehicle finish starting up
        rows = []
        drain(m, 3, rows, texts)
        last = [sorted(r[i] for r in rows)[len(rows) // 2] for i in range(1, 17)] if rows else [0] * 16
        ok_all = True
        for seq in range(1, 6):
            m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST, 0, seq, 0, 50, 2, 0, 0, 0)
            window = []
            drain(m, 3.0, window, texts)                    # 2 s of test plus the return to idle
            dev = [max((abs(r[i + 1] - last[i]) for r in window), default=0) for i in range(16)]
            moved = [i + 1 for i in range(16) if dev[i] >= 20]
            predicted = [i + 1 for i, f in enumerate(functions) if f in FUNCS[seq]]
            ok = moved == predicted
            ok_all = ok_all and ok
            per.append([frame, seq, NAMES[seq], ' '.join(map(str, predicted)) or 'none', ' '.join(map(str, moved)) or 'none', max(dev, default=0), ok])
            if window:
                last = list(window[-1][1:])
            drain(m, 1.0, [], texts)
        summary.update(status='ok', all_tests_match_the_vehicles_own_servo_functions=ok_all, status_text=' | '.join(dict.fromkeys(t for t in texts if 'otor' in t))[:200])
        return summary, per
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()


def main():
    os.makedirs(OUT, exist_ok=True)
    summaries, allrows = [], []
    for f in FRAMES:
        print('frame', f, flush=True)
        try:
            s, rows = one_frame(f, os.path.expanduser('~/rover-sweep/' + f))
        except Exception as e:
            s, rows = {'frame': f, 'status': 'exception: %r' % e}, []
        print(s, flush=True)
        summaries.append(s)
        allrows += rows
    with open(os.path.join(OUT, 'rover-sweep-per-test.csv'), 'w', newline='') as fh:
        w = csv.writer(fh, lineterminator='\n')
        w.writerow(['frame', 'param1', 'meaning', 'outputs_predicted_by_servo_functions', 'outputs_that_moved', 'max_deviation_us', 'match'])
        w.writerows(allrows)
    keys = ['frame', 'status', 'all_tests_match_the_vehicles_own_servo_functions', 'servo_functions_1_to_16', 'status_text']
    with open(os.path.join(OUT, 'rover-sweep-summary.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=keys, lineterminator='\n', extrasaction='ignore')
        w.writeheader()
        w.writerows(summaries)


main()
