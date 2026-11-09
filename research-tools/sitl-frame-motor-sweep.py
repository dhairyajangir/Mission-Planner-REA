"""Per-frame motor test sweep against disposable ArduCopter SITL instances (WSL, pymavlink). Simulator only.

For every multirotor frame in the list below this script:
  1. starts the SITL binary with --model <frame> (the binary resolves the frame's default parameters itself),
  2. reads FRAME_CLASS and FRAME_TYPE from the vehicle,
  3. sends MAV_CMD_DO_MOTOR_TEST for sequence numbers 1..N (10 percent, 1 s each) while recording SERVO_OUTPUT_RAW on the same link,
  4. reports which servo output rose for each sequence number,
  5. compares that with the testing_order tables parsed from libraries/AP_Motors/AP_MotorsMatrix.cpp of the same source tree
     (matrix frames only: quad, hexa, octa, octa-quad, y6, deca, dodeca-hexa; tri/single/coax use other motor classes and are observed only).

    python sitl-frame-motor-sweep.py <ardupilot tree> <out dir> [frame names ...]
"""
import csv
import os
import re
import subprocess
import sys
import time

from pymavlink import mavutil

TREE, OUT = sys.argv[1], sys.argv[2]
DEFAULT_FRAMES = ['quad', 'X', 'bfx', 'djix', 'cwx', 'hexa', 'hexax', 'hexa-cwx', 'hexa-dji', 'octa', 'octa-cwx', 'octa-dji',
                  'octa-quad', 'octa-quad-cwx', 'octa-quad-cor', 'octa-quad-cw-cor', 'deca', 'deca-cwx', 'y6', 'dodeca-hexa',
                  'hexadeca-octa', 'hexadeca-octa-cwx', 'tri', 'singlecopter', 'coaxcopter']
FRAMES = sys.argv[3:] or DEFAULT_FRAMES
MODEL_FOR = {'quad': '+'}          # sim_vehicle maps the "quad" frame to the "+" model
PCT, SECS, GAP = 10, 1.0, 0.8
# Non-matrix classes, transcribed BY HAND from _output_test_seq in AP_MotorsTri.cpp (pitch not reversed: motor1, motor4, tail servo = CH7, motor2),
# AP_MotorsSingle.cpp (servo1..servo6) and AP_MotorsCoax.cpp (servo1..servo6): sequence number -> servo output
HAND_SEQ = {7: [1, 4, 7, 2], 8: [1, 2, 3, 4, 5, 6], 9: [1, 2, 3, 4, 5, 6]}
MATRIX_CLASS = {'quad': 1, 'hexa': 2, 'octa': 3, 'octaquad': 4, 'y6': 5, 'dodecahexa': 12, 'deca': 14}


def parse_enums():
    h = open(os.path.join(TREE, 'libraries/AP_Motors/AP_Motors_Class.h')).read()
    return {m.group(1): int(m.group(2)) for m in re.finditer(r'(MOTOR_FRAME_(?:TYPE_)?[A-Z0-9_]+)\s*=\s*(\d+)', h)}


def parse_orders():
    """{(frame_class, frame_type or None for default): [testing_order per motor index]} from AP_MotorsMatrix.cpp."""
    enums = parse_enums()
    src = open(os.path.join(TREE, 'libraries/AP_Motors/AP_MotorsMatrix.cpp')).read()
    result = {}
    for fm in re.finditer(r'bool AP_MotorsMatrix::setup_(\w+?)_matrix\(motor_frame_type frame_type\)\s*\{', src):
        cls = MATRIX_CLASS.get(fm.group(1))
        if cls is None:
            continue
        end = src.find('\nbool AP_MotorsMatrix::', fm.end())
        body = src[fm.end(): end if end > 0 else len(src)]
        labels = []
        for tok in re.finditer(r'case (MOTOR_FRAME_TYPE_[A-Z0-9_]+):|default:|static const AP_MotorsMatrix::MotorDef(?:Raw)? motors\[\]\s*\{(.*?)\};', body, re.S):
            if tok.group(1):
                labels.append(enums[tok.group(1)])
            elif tok.group(0).startswith('default'):
                labels.append(None)
            else:
                orders = [int(re.findall(r'(\d+)\s*\}?\s*$', e.strip())[0]) for e in re.findall(r'\{([^{}]*)\}', tok.group(2))]
                for lab in labels:
                    result[(cls, lab)] = orders
                labels = []
    return result


ORDERS = parse_orders()


def expected_orders(cls, typ):
    return ORDERS.get((cls, typ)) or ORDERS.get((cls, None))


def start_sitl(frame, work):
    os.makedirs(work, exist_ok=True)
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
    time.sleep(1)
    log = open(os.path.join(work, 'sitl.log'), 'w')
    binary = os.path.join(TREE, 'build/sitl/bin/arducopter')
    wipe = [] if os.environ.get('SWEEP_NOWIPE') else ['-w']      # SWEEP_NOWIPE=1 keeps the stored parameters in <work>/eeprom.bin
    proc = subprocess.Popen([binary] + wipe + ['--model', MODEL_FOR.get(frame, frame), '-I', '0', '-s', '1',
                             '--home', '-35.363261,149.165230,584,0'], cwd=work, stdout=log, stderr=subprocess.STDOUT)
    return proc


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


def drain(m, secs, rows, texts):
    end = time.time() + secs
    while time.time() < end:
        msg = m.recv_match(type=['SERVO_OUTPUT_RAW', 'STATUSTEXT'], blocking=True, timeout=0.2)
        if msg is None:
            continue
        if msg.get_type() == 'SERVO_OUTPUT_RAW':
            rows.append([time.time()] + [getattr(msg, 'servo%d_raw' % i, 0) for i in range(1, 17)])
        else:
            texts.append((time.time(), msg.text))


def sweep_frame(frame, work):
    proc = start_sitl(frame, work)
    summary, seqrows = {'frame': frame}, []
    try:
        m = connect()
        if m is None:
            summary['status'] = 'no connection'
            return summary, seqrows
        cls, typ = get_param(m, 'FRAME_CLASS'), get_param(m, 'FRAME_TYPE')
        summary.update(frame_class=cls, frame_type=typ)
        exp = expected_orders(cls, typ) if cls in MATRIX_CLASS.values() else None
        hand = HAND_SEQ.get(cls)
        n = len(exp) if exp else (len(hand) if hand else 6)
        m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0, 36, 50000, 0, 0, 0, 0, 0)
        rows, texts = [], []
        drain(m, 4, rows, texts)
        idle = [sorted(r[i] for r in rows)[len(rows) // 2] for i in range(1, 17)] if rows else [0] * 16
        for seq in range(1, n + 1):
            t_start = time.time()
            m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST, 0,
                                    seq, 0, PCT, SECS, 1, 1, 0)   # motor seq, throttle type percent, percent, seconds, count 1, order SEQUENCE
            window = []
            drain(m, SECS + GAP, window, texts)
            # a servo output counts as moved when it leaves its idle value by 20 us or more in either direction (flap servos idle at 1500 and the 10 percent test drives them down to 1100)
            dev = [max((abs(r[i + 1] - idle[i]) for r in window), default=0) for i in range(16)]
            moved = [i + 1 for i in range(16) if dev[i] >= 20]
            peak = max(dev, default=0)
            want = None
            if exp:
                # sequence number seq runs the motor whose testing_order == seq; servo output = motor index + 1
                want = [i + 1 for i, o in enumerate(exp) if o == seq]
            elif hand:
                want = [hand[seq - 1]]
            seqrows.append([frame, cls, typ, seq, ' '.join(map(str, want)) if want is not None else 'n/a (no source table for this class)',
                            ' '.join(map(str, moved)) or 'none', peak])
        ok = [r for r in seqrows if r[4] == r[5]]
        summary.update(status='ok', motors_tested=n, expected_known=bool(exp or hand), sequences_matching_source=len(ok) if (exp or hand) else 'n/a',
                       idle_pwm=' '.join(map(str, idle[:n])), status_text=' | '.join(t for _, t in texts[:4]))
        return summary, seqrows
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
            s, r = sweep_frame(f, os.environ.get('SWEEP_WORKDIR') or os.path.expanduser('~/frame-sweep/' + f))
        except Exception as e:                      # keep failed attempts in the record
            s, r = {'frame': f, 'status': 'exception: %r' % e}, []
        print(s, flush=True)
        summaries.append(s)
        allrows += r
        os.system('cp %s %s 2>/dev/null' % (os.path.expanduser('~/frame-sweep/%s/sitl.log' % f), os.path.join(OUT, 'sitl-%s.log' % f)))
    with open(os.path.join(OUT, 'frame-sweep-sequences.csv'), 'w', newline='') as fh:
        w = csv.writer(fh, lineterminator='\n')
        w.writerow(['frame', 'frame_class', 'frame_type', 'sequence', 'expected_servo_from_source', 'observed_servos_moved_20us_or_more', 'peak_deviation_us'])
        w.writerows(allrows)
    keys = ['frame', 'status', 'frame_class', 'frame_type', 'motors_tested', 'expected_known', 'sequences_matching_source', 'idle_pwm', 'status_text']
    with open(os.path.join(OUT, 'frame-sweep-summary.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=keys, lineterminator='\n', extrasaction='ignore')
        w.writeheader()
        w.writerows(summaries)


main()
