"""Per-frame motor test sweep against disposable ArduCopter SITL instances (WSL, pymavlink). Simulator only.

For every multirotor frame in the list below this script:
  1. starts the SITL binary with --model <frame> (the binary resolves the frame's default parameters itself),
  2. reads FRAME_CLASS and FRAME_TYPE from the vehicle,
  3. sends MAV_CMD_DO_MOTOR_TEST for sequence numbers 1..N (10 percent, 1 s each) while recording SERVO_OUTPUT_RAW on the same link,
  4. reports which servo output rose for each sequence number,
  5. compares that with the testing_order tables parsed from libraries/AP_Motors/AP_MotorsMatrix.cpp of the same source tree
     (matrix frames only: quad, hexa, octa, octa-quad, y6, deca, dodeca-hexa; tri/single/coax use other motor classes and are observed only).

    python sitl-frame-motor-sweep.py <ardupilot tree> <out dir> [frame spec ...]

A frame spec is a simulator model name, optionally followed by :PARAM=VALUE[,PARAM=VALUE...] (set on a first start, then the simulator is restarted
without wiping its parameters, e.g. quad:FRAME_TYPE=19 for the Y4 type). Frames with a frame_example_script in vehicleinfo.json (the scripted motor matrices,
frame class 15 to 17) get SCR_ENABLE=1 on the first start and the example Lua script copied into <work>/scripts before the second start; their expected
servo order comes from the add_motor(...) lines of that script. SERVO_OUTPUT_RAW port 0 and port 1 are both read, so up to 32 outputs can be observed.
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
BINARY = os.environ.get('SWEEP_BINARY', 'arducopter')                  # SWEEP_BINARY=arduplane sweeps QuadPlane frames (motor test of the VTOL motors)
PREFIX = os.environ.get('SWEEP_PARAM_PREFIX', '')                       # 'Q_' for QuadPlane: Q_FRAME_CLASS and Q_FRAME_TYPE
INSTANCE = int(os.environ.get('SWEEP_INSTANCE', '0'))                   # tcp port 5760 + 10 * instance
PORT = 5760 + 10 * INSTANCE
# Non-matrix classes, transcribed BY HAND from _output_test_seq in AP_MotorsTri.cpp (pitch not reversed: motor1, motor4, tail servo = CH7, motor2),
# AP_MotorsSingle.cpp (servo1..servo6) and AP_MotorsCoax.cpp (servo1..servo6): sequence number -> servo output
HAND_SEQ = {7: [1, 4, 7, 2], 8: [1, 2, 3, 4, 5, 6], 9: [1, 2, 3, 4, 5, 6]}
LUA_FRAMES = {'dotriaconta_octaquad_x': 'MotorMatrix_dotriaconta_octaquad_x.lua', 'hexadeca-octa': 'MotorMatrix_hexadeca_octa.lua', 'hexadeca-octa-cwx': 'MotorMatrix_hexadeca_octa_cw_x.lua'}
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


def lua_orders(name):
    """[testing_order per motor number] from the add_motor(AP_MOTORS_MOT_n, angle, yaw, order) lines of a frame example script."""
    text = open(os.path.join(TREE, 'libraries/AP_Scripting/examples', LUA_FRAMES[name])).read()
    if name == 'dotriaconta_octaquad_x':
        # this script adds its motors in a loop, so the lines cannot be matched one by one: read NUM_BANKS and apply the loop body by hand
        # (motors 4*b+0..3 of bank b have testing orders 4*b+1, 4*b+3, 4*b+4, 4*b+2, from the add_motor lines inside the for loop)
        banks = int(re.search(r'local NUM_BANKS = (\d+)', text).group(1))
        return [4 * b + o for b in range(banks) for o in (1, 3, 4, 2)]
    found = {int(m.group(1)): int(m.group(4)) for m in re.finditer(r'add_motor\(AP_MOTORS_MOT_(\d+),\s*(-?[\d.]+),\s*AP_MOTORS_MATRIX_YAW_FACTOR_(CW|CCW),\s*(\d+)\s*\)', text)}
    return [found[n] for n in sorted(found)]


def expected_orders(cls, typ):
    return ORDERS.get((cls, typ)) or ORDERS.get((cls, None))


def start_sitl(frame, work, wipe=None):
    os.makedirs(work, exist_ok=True)
    subprocess.call(['pkill', '-f', 'build/sitl/bin/' + BINARY])
    time.sleep(1)
    log = open(os.path.join(work, 'sitl.log'), 'a')
    binary = os.path.join(TREE, 'build/sitl/bin/' + BINARY)
    if wipe is None:
        wipe = not os.environ.get('SWEEP_NOWIPE')       # SWEEP_NOWIPE=1 keeps the stored parameters in <work>/eeprom.bin
    proc = subprocess.Popen([binary] + (['-w'] if wipe else []) + ['--model', MODEL_FOR.get(frame, frame), '-I', str(INSTANCE), '-s', '1',
                             '--home', '-35.363261,149.165230,584,0'], cwd=work, stdout=log, stderr=subprocess.STDOUT)
    return proc


def prepare(frame, work, params):
    """First start: set params (and SCR_ENABLE for scripted frames), stop; the caller then restarts without wiping. Returns True if a restart is needed."""
    if not params and frame not in LUA_FRAMES:
        return False
    subprocess.call(['rm', '-rf', work])
    proc = start_sitl(frame, work, wipe=True)
    try:
        m = connect()
        if m is None:
            raise RuntimeError('no connection during preparation')
        want = dict(params)
        if frame in LUA_FRAMES:
            want['SCR_ENABLE'] = 1
        for name, value in want.items():
            for _ in range(5):
                m.mav.param_set_send(m.target_system, m.target_component, name.encode(), float(value), mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
                time.sleep(0.5)
                if get_param(m, name) == int(value):
                    break
            else:
                raise RuntimeError('could not set %s' % name)
        time.sleep(2)
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
    if frame in LUA_FRAMES:
        os.makedirs(os.path.join(work, 'scripts'), exist_ok=True)
        subprocess.call(['cp', os.path.join(TREE, 'libraries/AP_Scripting/examples', LUA_FRAMES[frame]), os.path.join(work, 'scripts')])
    return True


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


STATE = [0] * 32


def drain(m, secs, rows, texts):
    end = time.time() + secs
    while time.time() < end:
        msg = m.recv_match(type=['SERVO_OUTPUT_RAW', 'STATUSTEXT'], blocking=True, timeout=0.2)
        if msg is None:
            continue
        if msg.get_type() == 'SERVO_OUTPUT_RAW':
            base = 16 * getattr(msg, 'port', 0)
            for i in range(1, 17):
                STATE[base + i - 1] = getattr(msg, 'servo%d_raw' % i, 0)
            rows.append([time.time()] + list(STATE))
        else:
            texts.append((time.time(), msg.text))


def sweep_frame(spec, work):
    frame, _, ptext = spec.partition(':')
    params = dict((kv.split('=')[0], float(kv.split('=')[1])) for kv in ptext.split(',')) if ptext else {}
    restart = prepare(frame, work, params)
    proc = start_sitl(frame, work, wipe=not restart and not os.environ.get('SWEEP_NOWIPE'))
    summary, seqrows = {'frame': spec}, []
    try:
        m = connect()
        if m is None:
            summary['status'] = 'no connection'
            return summary, seqrows
        cls, typ = get_param(m, PREFIX + 'FRAME_CLASS'), get_param(m, PREFIX + 'FRAME_TYPE')
        summary.update(frame_class=cls, frame_type=typ)
        exp = expected_orders(cls, typ) if cls in MATRIX_CLASS.values() else None
        if frame in LUA_FRAMES:
            exp = lua_orders(frame)                # scripted matrix: the order comes from the example script that was installed
            time.sleep(8)                           # let the script create the matrix
        hand = HAND_SEQ.get(cls)                                   # motor numbers; for a QuadPlane they are mapped to outputs through the vehicle's own SERVOn_FUNCTION values
        n = len(exp) if exp else (len(hand) if hand else (4 if (PREFIX and cls == 10) else 6))
        servo_of_motor = None
        if PREFIX:
            funcs = [get_param(m, 'SERVO%d_FUNCTION' % i) for i in range(1, 17)]
            servo_of_motor = {f - 32: i + 1 for i, f in enumerate(funcs) if f is not None and 33 <= f <= 40}
            thrust_outputs = {i + 1 for i, f in enumerate(funcs) if f in (70, 73, 74, 75, 76)}      # throttle, throttle left/right and tilt left/right: tailsitter outputs are on these, not on Motor1..8
            func_servo = {f: i + 1 for i, f in reversed(list(enumerate(funcs))) if f is not None}
            summary['servo_functions_1_to_16'] = ' '.join(str(f) for f in funcs)
            summary['servo_of_motor'] = ' '.join('%d:%d' % kv for kv in sorted(servo_of_motor.items()))
        m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0, 36, 50000, 0, 0, 0, 0, 0)
        rows, texts = [], []
        drain(m, 4, rows, texts)
        idle = [sorted(r[i] for r in rows)[len(rows) // 2] for i in range(1, 33)] if rows else [0] * 32
        for seq in range(1, n + 1):
            m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST, 0,
                                    seq, 0, PCT, SECS, 1, 1, 0)   # motor seq, throttle type percent, percent, seconds, count 1, order SEQUENCE
            window = []
            drain(m, SECS + GAP, window, texts)
            # a servo output counts as moved when it leaves its idle value by 20 us or more in either direction (flap servos idle at 1500 and the 10 percent test drives them down to 1100)
            dev = [max((abs(r[i + 1] - idle[i]) for r in window), default=0) for i in range(32)]
            moved = [i + 1 for i in range(32) if dev[i] >= 20]
            if servo_of_motor is not None:
                # on a QuadPlane the control-surface outputs move by themselves while the vehicle sits there, so only the outputs assigned to a motor function are looked at
                moved = [i for i in moved if i in set(servo_of_motor.values()) | thrust_outputs]
            peak = max(dev, default=0)
            want = None
            if exp:
                # sequence number seq runs the motor whose testing_order == seq; servo output = motor index + 1 for ArduCopter, and for a QuadPlane (SWEEP_PARAM_PREFIX=Q_)
                # the output whose SERVOn_FUNCTION is Motor<k> (function 32 + k), read from the vehicle itself
                want = [i + 1 for i, o in enumerate(exp) if o == seq]
                if servo_of_motor is not None:
                    want = [servo_of_motor.get(k) for k in want]
            elif hand:
                want = [hand[seq - 1]] if servo_of_motor is None else [servo_of_motor.get(hand[seq - 1])]
            if PREFIX and cls == 10 and seq <= 4:
                # AP_MotorsTailsitter::_output_test_seq: 1 right throttle (74), 2 right tilt servo (76), 3 left throttle (73), 4 left tilt servo (75)
                want = [func_servo.get((74, 76, 73, 75)[seq - 1])]
            seqrows.append([spec, cls, typ, seq, ' '.join(map(str, want)) if want is not None else 'n/a (no source table for this class)',
                            ' '.join(map(str, moved)) or 'none', peak])
        ok = [r for r in seqrows if r[4] == r[5]]
        summary.update(status='ok', motors_tested=n, expected_known=bool(exp or hand or (PREFIX and cls == 10)), sequences_matching_source=len(ok) if (exp or hand or (PREFIX and cls == 10)) else 'n/a',
                       idle_pwm=' '.join(map(str, idle[:n])), status_text=' | '.join(t for _, t in texts[:4]), motor_messages=' | '.join(dict.fromkeys(t for _, t in texts if 'otor' in t))[:300])
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
            s, r = sweep_frame(f, os.environ.get('SWEEP_WORKDIR') or os.path.expanduser('~/frame-sweep/' + f.replace(':', '_').replace('=', '-').replace(',', '_')))
        except Exception as e:                      # keep failed attempts in the record
            s, r = {'frame': f, 'status': 'exception: %r' % e}, []
        print(s, flush=True)
        summaries.append(s)
        allrows += r
        tag = f.replace(':', '_').replace('=', '-').replace(',', '_')
        os.system('cp %s %s 2>/dev/null' % (os.path.expanduser('~/frame-sweep/%s/sitl.log' % tag), os.path.join(OUT, 'sitl-%s.log' % tag)))
    with open(os.path.join(OUT, 'frame-sweep-sequences.csv'), 'w', newline='') as fh:
        w = csv.writer(fh, lineterminator='\n')
        w.writerow(['frame', 'frame_class', 'frame_type', 'sequence', 'expected_servo_from_source', 'observed_servos_moved_20us_or_more', 'peak_deviation_us'])
        w.writerows(allrows)
    keys = ['frame', 'status', 'frame_class', 'frame_type', 'servo_of_motor', 'motors_tested', 'expected_known', 'sequences_matching_source', 'idle_pwm', 'servo_functions_1_to_16', 'motor_messages', 'status_text']
    with open(os.path.join(OUT, 'frame-sweep-summary.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=keys, lineterminator='\n', extrasaction='ignore')
        w.writeheader()
        w.writerows(summaries)


main()
