"""Motor test across the ArduSub frame configurations on disposable ArduSub SITLs (WSL, pymavlink). Simulator only.

ArduSub's MAV_CMD_DO_MOTOR_TEST handler differs from ArduCopter's: it only accepts the "board order" test type (param6 = 2), the vehicle must be armed, the
command has to be repeated at least twice a second or the test times out and disarms, and motor number n means output n (not a sequence). For each FRAME_CONFIG
value this script starts the simulator (the first start sets FRAME_CONFIG, the simulator is restarted without wiping parameters), force-arms, then for n = 1..12
sends the test for output n at 10 percent every 0.25 s for 1.2 s while recording SERVO_OUTPUT_RAW on the same link, and reports which outputs left their idle
value by 20 us or more. The expected set of motors for each configuration comes from the add_motor_raw_6dof(...) lines of AP_Motors6DOF.cpp in the same source tree
(SUB_FRAME_CUSTOM falls through to SIMPLEROV_3 there, as the C++ switch does).

    python sitl-sub-frame-motor-sweep.py <ardupilot tree> <out dir>
"""
import csv
import os
import re
import subprocess
import sys
import time

from pymavlink import mavutil

TREE, OUT = sys.argv[1], sys.argv[2]
CONFIGS = [(0, 'BLUEROV1'), (1, 'VECTORED'), (2, 'VECTORED_6DOF'), (3, 'VECTORED_6DOF_90DEG'), (4, 'SIMPLEROV_3'), (5, 'SIMPLEROV_4'), (6, 'SIMPLEROV_5'), (7, 'CUSTOM')]


def parse_expected():
    h = open(os.path.join(TREE, 'libraries/AP_Motors/AP_Motors6DOF.h')).read()
    enum = re.search(r'typedef enum \{(.*?)\} sub_frame_t;', h, re.S).group(1)
    names = [n.strip() for n in re.findall(r'(SUB_FRAME_[A-Z0-9_]+)', enum)]
    values = {n: i for i, n in enumerate(names)}          # no explicit values in the enum: they count from 0
    src = open(os.path.join(TREE, 'libraries/AP_Motors/AP_Motors6DOF.cpp')).read()
    body = src[src.index('void AP_Motors6DOF::setup_motors'):src.index('void AP_Motors6DOF::add_motor_raw_6dof')]
    body = re.sub(r'//[^\n]*', '', body)                # a commented-out 'break;' (SUB_FRAME_CUSTOM) must not end its case
    cases = {}
    labels, motors = [], []
    for tok in re.finditer(r'case (SUB_FRAME_[A-Z0-9_]+):|default:|add_motor_raw_6dof\(AP_MOTORS_MOT_(\d+),|\bbreak;', body):
        if tok.group(1):
            if motors:
                labels, motors = [], []
            labels.append(tok.group(1))
        elif tok.group(0) == 'default:':
            if motors:
                labels, motors = [], []
            labels.append('default')
        elif tok.group(2):
            motors.append(int(tok.group(2)))
            for lab in labels:
                cases[lab] = list(motors)
        else:
            labels, motors = [], []
    out = {}
    for name, v in values.items():
        if name in cases:
            out[v] = cases[name]
    # frame configs not named in the switch use the default case
    for v in values.values():
        out.setdefault(v, cases.get('default', []))
    return out, values


def start(work, wipe):
    os.makedirs(work, exist_ok=True)
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
    time.sleep(1)
    return subprocess.Popen([os.path.join(TREE, 'build/sitl/bin/ardusub')] + (['-w'] if wipe else []) + ['--model', 'vectored', '-I', '0', '-s', '1',
                             '--home', '-35.363261,149.165230,-0.5,0'], cwd=work, stdout=open(os.path.join(work, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)


def connect():
    t0 = time.time()
    while time.time() - t0 < 60:
        try:
            m = mavutil.mavlink_connection('tcp:127.0.0.1:5760', autoreconnect=False)
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


def stop(proc):
    proc.terminate()
    try:
        proc.wait(10)
    except Exception:
        proc.kill()


def drain(m, secs, rows, texts, send=None):
    end = time.time() + secs
    last = 0
    while time.time() < end:
        if send and time.time() - last > 0.25:
            send()
            last = time.time()
        msg = m.recv_match(type=['SERVO_OUTPUT_RAW', 'STATUSTEXT'], blocking=True, timeout=0.1)
        if msg is None:
            continue
        if msg.get_type() == 'SERVO_OUTPUT_RAW':
            rows.append([time.time()] + [getattr(msg, 'servo%d_raw' % i, 0) for i in range(1, 17)])
        else:
            texts.append(msg.text)


def one_config(value, name, expected, work):
    subprocess.call(['rm', '-rf', work])
    proc = start(work, True)
    try:
        m = connect()
        if m is None:
            return {'frame_config': value, 'name': name, 'status': 'no connection (first start)'}, []
        for _ in range(5):
            m.mav.param_set_send(m.target_system, m.target_component, b'FRAME_CONFIG', float(value), mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
            time.sleep(0.5)
            if get_param(m, 'FRAME_CONFIG') == value:
                break
        time.sleep(2)
    finally:
        stop(proc)
    proc = start(work, False)
    try:
        m = connect()
        if m is None:
            return {'frame_config': value, 'name': name, 'status': 'no connection (second start)'}, []
        got = get_param(m, 'FRAME_CONFIG')
        m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0, 36, 50000, 0, 0, 0, 0, 0)
        rows, texts = [], []
        drain(m, 25, rows, texts)                                     # let the vehicle finish starting up
        m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 21196, 0, 0, 0, 0, 0)
        rows = []
        drain(m, 3, rows, texts)
        idle = [sorted(r[i] for r in rows)[len(rows) // 2] for i in range(1, 17)] if rows else [0] * 16
        per = []
        for n in range(1, 13):
            def send(n=n):
                m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST, 0, n, 0, 10, 1, 1, 2, 0)
            window = []
            drain(m, 1.2, window, texts, send)
            dev = [max((abs(r[i + 1] - idle[i]) for r in window), default=0) for i in range(16)]
            moved = [i + 1 for i in range(16) if dev[i] >= 20]
            per.append([value, name, n, ' '.join(map(str, moved)) or 'none', max(dev, default=0)])
            drain(m, 0.5, [], texts)
        m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 0, 21196, 0, 0, 0, 0, 0)
        want = set(expected.get(value, []))
        moved_by_test = {r[2] for r in per if r[3] == str(r[2])}
        extra = [r for r in per if r[3] not in ('none', str(r[2]))]
        ok = moved_by_test == want and not extra
        return {'frame_config': value, 'name': name, 'status': 'ok', 'frame_config_read_back': got, 'expected_motors': ' '.join(map(str, sorted(want))),
                'outputs_that_moved_for_their_own_number': ' '.join(map(str, sorted(moved_by_test))), 'tests_that_moved_other_outputs': len(extra),
                'matches_source': ok, 'status_text': ' | '.join(dict.fromkeys(texts))[:200]}, per
    finally:
        stop(proc)


def main():
    os.makedirs(OUT, exist_ok=True)
    expected, _ = parse_expected()
    summaries, allrows = [], []
    for value, name in CONFIGS:
        print('FRAME_CONFIG', value, name, flush=True)
        try:
            s, rows = one_config(value, name, expected, os.path.expanduser('~/sub-sweep/%d' % value))
        except Exception as e:
            s, rows = {'frame_config': value, 'name': name, 'status': 'exception: %r' % e}, []
        print(s, flush=True)
        summaries.append(s)
        allrows += rows
    with open(os.path.join(OUT, 'sub-sweep-per-output.csv'), 'w', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['frame_config', 'name', 'output_tested', 'outputs_that_moved', 'max_deviation_us'])
        w.writerows(allrows)
    keys = ['frame_config', 'name', 'status', 'frame_config_read_back', 'expected_motors', 'outputs_that_moved_for_their_own_number', 'tests_that_moved_other_outputs', 'matches_source', 'status_text']
    with open(os.path.join(OUT, 'sub-sweep-summary.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys, lineterminator='\n', extrasaction='ignore')
        w.writeheader()
        w.writerows(summaries)


main()
