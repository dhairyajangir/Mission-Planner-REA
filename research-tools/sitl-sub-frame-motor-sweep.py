"""Motor test across the ArduSub frame configurations on disposable ArduSub SITLs (WSL, pymavlink). Simulator only.

ArduSub's MAV_CMD_DO_MOTOR_TEST handler differs from ArduCopter's: it only accepts the "board order" test type (param6 = 2), the vehicle must be armed, the
command has to be repeated at least twice a second or the test times out and disarms, and motor number param1 is a zero-based output number (not a sequence). For each FRAME_CONFIG
value this script starts the simulator (the first start sets FRAME_CONFIG, the simulator is restarted without wiping parameters), force-arms, then for param1 = 0..11
sends the test for output n at 10 percent every 0.25 s for 1.4 s, back to back with the next output while recording SERVO_OUTPUT_RAW on the same link, and reports which outputs left their idle
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
INSTANCE = int(os.environ.get('SWEEP_INSTANCE', '0'))       # simulator instance: serial 0 listens on tcp 5760 + 10 * instance, so a second sweep can run beside another autotest
PORT = 5760 + 10 * INSTANCE
ONLY = [int(x) for x in os.environ.get('SWEEP_CONFIGS', '').split(',') if x]             # e.g. SWEEP_CONFIGS=2,3
EXTRA = dict((kv.split('=')[0], float(kv.split('=')[1])) for kv in os.environ.get('SWEEP_EXTRA_PARAMS', '').split(',') if kv)   # e.g. SERVO8_FUNCTION=40
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
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardusub'])      # only this vehicle: another autotest may be running

    time.sleep(1)
    return subprocess.Popen([os.path.join(TREE, 'build/sitl/bin/ardusub')] + (['-w'] if wipe else []) + ['--model', 'vectored', '-I', str(INSTANCE), '-s', '1',
                             '--home', '-35.363261,149.165230,-0.5,0'], cwd=work, stdout=open(os.path.join(work, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)


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
        for pname, pvalue in [('FRAME_CONFIG', float(value))] + list(EXTRA.items()):
            for _ in range(5):
                m.mav.param_set_send(m.target_system, m.target_component, pname.encode(), pvalue, mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
                time.sleep(0.5)
                if get_param(m, pname) == int(pvalue):
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
        last = list(idle)
        for n in range(0, 12):                                         # param1 is the zero-based output: AP_MotorsMatrix::output_test_num(output_channel) calls rc_write(output_channel)
            def send(n=n):
                m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST, 0, n, 0, 10, 1, 1, 2, 0)
            # the vehicle ends the test (and disarms) if no motor test command arrives for 500 ms, so the commands for the next output follow at once;
            # an output that was tested earlier stays at its test value, so "moved" means: left its value at the start of this window by 20 us or more
            window = []
            drain(m, 1.4, window, texts, send)
            dev = [max((abs(r[i + 1] - last[i]) for r in window), default=0) for i in range(16)]
            moved = [i + 1 for i in range(16) if dev[i] >= 20]
            per.append([value, name, n, ' '.join(map(str, moved)) or 'none', max(dev, default=0)])
            if window:
                last = list(window[-1][1:])
        m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 0, 21196, 0, 0, 0, 0, 0)
        want = set(expected.get(value, []))                           # motor numbers, one-based: motor k is servo output k
        moved_by_test = {r[2] + 1 for r in per if r[3] == str(r[2] + 1)}
        extra = [r for r in per if r[3] not in ('none', str(r[2] + 1))]
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
        if ONLY and value not in ONLY:
            continue
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
        w.writerow(['frame_config', 'name', 'param1_zero_based_output', 'servo_outputs_that_moved', 'max_deviation_us'])
        w.writerows(allrows)
    keys = ['frame_config', 'name', 'status', 'frame_config_read_back', 'expected_motors', 'outputs_that_moved_for_their_own_number', 'tests_that_moved_other_outputs', 'matches_source', 'status_text']
    with open(os.path.join(OUT, 'sub-sweep-summary.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys, lineterminator='\n', extrasaction='ignore')
        w.writeheader()
        w.writerows(summaries)


main()
