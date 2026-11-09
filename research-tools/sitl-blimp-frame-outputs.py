"""Observe which servo outputs each stick axis moves on the two ArduBlimp simulator frames (blimp = fins, FRAME_CLASS 1; blimp-motor = motors, FRAME_CLASS 2).
Disposable Blimp SITLs (WSL, pymavlink), simulator only. There is no motor-test command in ArduBlimp, and no source table to predict from, so this is an observation,
not a check: the vehicle is put in MANUAL, force-armed, and each of RC channels 1 to 4 is overridden in turn to 1900 (others 1500) for 2 s while SERVO_OUTPUT_RAW is
recorded on the same link; an output counts as moved if it left its value at the start of that step by 20 us or more.

    python sitl-blimp-frame-outputs.py <ardupilot tree> <out dir>
"""
import csv
import os
import subprocess
import sys
import time

from pymavlink import mavutil

TREE, OUT = sys.argv[1], sys.argv[2]
INSTANCE = int(os.environ.get('SWEEP_INSTANCE', '0'))
PORT = 5760 + 10 * INSTANCE
FRAMES = ['blimp', 'blimp-motor']


def start(frame, work):
    os.makedirs(work, exist_ok=True)
    subprocess.call(['pkill', '-f', 'build/sitl/bin/blimp'])
    time.sleep(1)
    return subprocess.Popen([os.path.join(TREE, 'build/sitl/bin/blimp'), '-w', '--model', frame, '-I', str(INSTANCE), '-s', '1', '--home', '-35.363261,149.165230,584,0'],
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
            return r.param_value
    return None


def rc(m, ch=None, value=1900):
    vals = [1500] * 8 + [65535] * 10
    if ch:
        vals[ch - 1] = value
    m.mav.rc_channels_override_send(m.target_system, m.target_component, *vals)


def drain(m, secs, rows, texts, send=None):
    end = time.time() + secs
    last = 0
    while time.time() < end:
        if send and time.time() - last > 0.1:
            send()
            last = time.time()
        msg = m.recv_match(type=['SERVO_OUTPUT_RAW', 'STATUSTEXT'], blocking=True, timeout=0.05)
        if msg is None:
            continue
        if msg.get_type() == 'SERVO_OUTPUT_RAW':
            rows.append([time.time()] + [getattr(msg, 'servo%d_raw' % i, 0) for i in range(1, 9)])
        else:
            texts.append(msg.text)


def one(frame, work):
    subprocess.call(['rm', '-rf', work])
    proc = start(frame, work)
    summary, per = {'frame': frame}, []
    try:
        m = connect()
        if m is None:
            summary['status'] = 'no connection'
            return summary, per
        for name in ('FRAME_CLASS', 'SERVO1_FUNCTION', 'SERVO2_FUNCTION', 'SERVO3_FUNCTION', 'SERVO4_FUNCTION', 'SERVO1_MIN', 'SERVO1_MAX', 'SERVO1_TRIM'):
            summary[name] = get_param(m, name)
        m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0, 36, 50000, 0, 0, 0, 0, 0)
        texts = []
        drain(m, 25, [], texts)
        m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0, 1, 1, 0, 0, 0, 0, 0)    # MANUAL (custom mode 1)
        drain(m, 1, [], texts, lambda: rc(m))
        m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 21196, 0, 0, 0, 0, 0)
        rows = []
        drain(m, 2, rows, texts, lambda: rc(m))
        summary['armed_text'] = ' | '.join(t for t in texts if 'rm' in t)[:120]
        base = [sorted(r[i] for r in rows)[len(rows) // 2] for i in range(1, 9)] if rows else [0] * 8
        last = list(base)
        for ch in (None, 1, 2, 3, 4):
            window = []
            drain(m, 2.0, window, texts, (lambda ch=ch: rc(m, ch)))
            dev = [max((abs(r[i + 1] - last[i]) for r in window), default=0) for i in range(8)]
            moved = ['%d(%+d)' % (i + 1, (window[-1][i + 1] - last[i])) for i in range(8) if dev[i] >= 20] if window else []
            per.append([frame, 'none' if ch is None else 'RC%d to 1900' % ch, ' '.join(moved) or 'none', max(dev, default=0)])
            if window:
                last = list(window[-1][1:])
            drain(m, 1.0, [], texts, lambda: rc(m))
            if window:
                last = list(base)
        summary['status'] = 'ok'
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
            s, rows = one(f, os.path.expanduser('~/blimp-frames/' + f))
        except Exception as e:
            s, rows = {'frame': f, 'status': 'exception: %r' % e}, []
        print(s, flush=True)
        summaries.append(s)
        allrows += rows
    with open(os.path.join(OUT, 'blimp-frame-outputs.csv'), 'w', newline='') as fh:
        w = csv.writer(fh, lineterminator='\n')
        w.writerow(['frame', 'stick_step', 'servo_outputs_that_moved_(change_in_us)', 'max_deviation_us'])
        w.writerows(allrows)
    keys = ['frame', 'status', 'FRAME_CLASS', 'SERVO1_FUNCTION', 'SERVO2_FUNCTION', 'SERVO3_FUNCTION', 'SERVO4_FUNCTION', 'SERVO1_MIN', 'SERVO1_MAX', 'SERVO1_TRIM', 'armed_text']
    with open(os.path.join(OUT, 'blimp-frame-summary.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=keys, lineterminator='\n', extrasaction='ignore')
        w.writeheader()
        w.writerows(summaries)


main()
