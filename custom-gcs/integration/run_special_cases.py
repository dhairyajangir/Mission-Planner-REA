"""Special Copter cases for the prototype's motor test, against disposable simulators (WSL, ArduPilot SITL, pymavlink). Simulator only.

1. Motor-to-output mappings that are not the default (SERVOn_FUNCTION changed on a quad): two motors swapped, motor 1 on output 9, motor 4 on no output. The plan is derived
   from the vehicle's own SERVOn_FUNCTION values, so a pass shows the firmware follows them.
2. The three scripted matrix frames (frame class 15): the example Lua script is installed and scripting enabled; the prototype cannot see the script, so it runs one
   discovery step per assigned motor output. The observed sequence is then compared with the testing orders read from the Lua file itself (independent of the vehicle).

    python3 run_special_cases.py <ardupilot tree> <out dir>
"""
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from customgcs import link, motors  # noqa: E402

TREE, OUT = sys.argv[1], sys.argv[2]
WORK = os.path.expanduser('~/cg-special')
HOME = '-35.363261,149.165230,584,0'
LUA = {'6dof-hex': 'Motors_6DoF.lua', 'setup-plus-quad': 'MotorMatrix_setup.lua', 'fault-tolerant-hex': 'MotorMatrix_fault_tolerant_hex.lua', '6dof-quad': 'Copter_Motors_6DoF.lua', 'dotriaconta_octaquad_x': 'MotorMatrix_dotriaconta_octaquad_x.lua', 'hexadeca-octa': 'MotorMatrix_hexadeca_octa.lua', 'hexadeca-octa-cwx': 'MotorMatrix_hexadeca_octa_cw_x.lua'}
CASES = [
    ('remap-swap-motors-1-and-2', '+', {'SERVO1_FUNCTION': 34, 'SERVO2_FUNCTION': 33}, None),
    ('remap-motor-1-on-output-9', '+', {'SERVO1_FUNCTION': 0, 'SERVO9_FUNCTION': 33}, None),
    ('remap-motor-4-unassigned', '+', {'SERVO4_FUNCTION': 0}, None),
    ('scripted-dotriaconta_octaquad_x', 'dotriaconta_octaquad_x', {'SCR_ENABLE': 1}, 'dotriaconta_octaquad_x'),
    ('scripted-hexadeca-octa', 'hexadeca-octa', {'SCR_ENABLE': 1}, 'hexadeca-octa'),
    ('scripted-hexadeca-octa-cwx', 'hexadeca-octa-cwx', {'SCR_ENABLE': 1}, 'hexadeca-octa-cwx'),
    ('scripted-setup-plus-quad', '+', {'SCR_ENABLE': 1, 'FRAME_CLASS': 15}, 'setup-plus-quad'),
    ('scripted-fault-tolerant-hex', 'hexa', {'SCR_ENABLE': 1, 'FRAME_CLASS': 15}, 'fault-tolerant-hex'),
    ('scripted-6dof-quad-class-16', '+', {'SCR_ENABLE': 1, 'FRAME_CLASS': 16}, '6dof-quad'),
    ('scripted-6dof-reversible-hex-class-16', 'hexa', {'SCR_ENABLE': 1, 'FRAME_CLASS': 16}, '6dof-hex'),
]


def start(model, wipe):
    return subprocess.Popen([os.path.join(TREE, 'build/sitl/bin/arducopter')] + (['-w'] if wipe else []) + ['--model', model, '-I', '0', '-s', '1', '--home', HOME],
                            cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)


def stop(proc):
    proc.terminate()
    try:
        proc.wait(10)
    except Exception:
        proc.kill()


def set_param(conn, name, value):
    from pymavlink import mavutil
    for _ in range(8):
        conn.mav.param_set_send(conn.target_system, conn.target_component, name.encode(), float(value), mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
        time.sleep(0.6)
        conn.mav.param_request_read_send(conn.target_system, conn.target_component, name.encode(), -1)
        reply = conn.recv_match(type='PARAM_VALUE', blocking=True, timeout=2)
        if reply is not None and reply.param_id.rstrip('\x00') == name and int(reply.param_value) == int(value):
            return
    raise RuntimeError('could not set %s' % name)


def lua_orders(key):
    """Testing order per motor number from the example script: [order of motor 1, order of motor 2, ...]."""
    text = open(os.path.join(TREE, 'libraries/AP_Scripting/examples', LUA[key])).read()
    if key == 'dotriaconta_octaquad_x':      # the script adds its motors in a loop: NUM_BANKS banks of four with testing orders 4b+1, 4b+3, 4b+4, 4b+2
        banks = int(re.search(r'local NUM_BANKS = (\d+)', text).group(1))
        return [4 * b + o for b in range(banks) for o in (1, 3, 4, 2)]
    found = {int(m.group(1)): int(m.group(4)) for m in re.finditer(r'add_motor\(AP_MOTORS_MOT_(\d+),\s*(-?[\d.]+),\s*AP_MOTORS_MATRIX_YAW_FACTOR_(CW|CCW),\s*(\d+)\s*\)', text)}
    if not found:         # add_motor_raw(zero-based motor, roll, pitch, yaw, testing order) of MotorMatrix_setup.lua
        found = {int(m.group(1)) + 1: int(m.group(2)) for m in re.finditer(r'MotorsMatrix:add_motor_raw\(\s*(\d+)\s*,[^,]+,[^,]+,[^,]+,\s*(\d+)\s*\)', text)}
    if not found:         # Motors_6DoF:add_motor(zero-based motor, roll, pitch, yaw, throttle, forward, lateral, reversible, testing order)
        found = {int(m.group(1)) + 1: int(m.group(2)) for m in re.finditer(r'Motors_6DoF:add_motor\(\s*(\d+)\s*,(?:[^,]+,){7}\s*(\d+)\s*\)', text)}
    return [found[n] for n in sorted(found)]


def run_case(name, model, params, lua_key):
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(os.path.join(WORK, 'scripts'))
    proc = start(model, True)
    try:
        conn, _ = link.connect(5760)
        time.sleep(15)
        for k, v in params.items():
            set_param(conn, k, v)
        time.sleep(2)
    finally:
        stop(proc)
    if lua_key:
        subprocess.call(['cp', os.path.join(TREE, 'libraries/AP_Scripting/examples', LUA[lua_key]), os.path.join(WORK, 'scripts')])
    proc = start(model, False)
    try:
        conn, mav_type = link.connect(5760)
        time.sleep(20 if lua_key else 0)                       # the script has to run before the matrix exists
        parameters = link.read_params(conn)
        info = link.detect(parameters, mav_type)
        lines = ['vehicle: %s, FRAME_CLASS %s, FRAME_TYPE %s, %d parameters' % (info.kind, info.frame_class, info.frame_type, len(parameters))]
        results = link.run_motor_test(conn, info, parameters, 10.0)
        for r in results:
            lines.append('%-48s expected=%-24s moved=%-24s %s %s' % (r.label, r.expected, r.moved, 'OK' if r.ok else 'MISMATCH', r.note))
        good = sum(1 for r in results if r.ok)
        lines.append('RESULT %d of %d steps matched' % (good, len(results)))
        ok = good == len(results)
        if lua_key:
          try:
            orders = lua_orders(lua_key)
            seq_to_motor = {order: motor + 1 for motor, order in enumerate(orders)}
            servo_of_motor = motors.servo_of_motor(parameters)
            predicted = [servo_of_motor.get(seq_to_motor[n], seq_to_motor[n]) for n in range(1, len(orders) + 1)]      # no SERVOn_FUNCTION parameter exists for outputs above 16: motor n is assumed on output n there (as in the sweep)
            observed = [r.moved[0] for r in results[:len(orders)] if len(r.moved) == 1]
            same = observed == predicted
            lines.append('LUA CHECK testing orders read from the script file predict outputs %s' % ' '.join(map(str, predicted)))
            lines.append('LUA CHECK observed %s: %s' % (' '.join(map(str, observed)), 'SAME' if same else 'DIFFERENT'))
            ok = ok and same
          except Exception as e:                                # keep the steps already recorded
            lines.append('LUA CHECK EXCEPTION %r' % (e,))
            ok = False
        return lines, ok
    finally:
        stop(proc)


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
    time.sleep(1)
    for name, model, params, lua_key in CASES:
        path = os.path.join(OUT, name + '.txt')
        if os.path.exists(path):
            continue
        t0 = time.time()
        try:
            lines, ok = run_case(name, model, params, lua_key)
        except Exception as e:                                  # keep the failure as the record
            lines, ok = ['EXCEPTION %r' % (e,)], False
        with open(path, 'w') as f:
            f.write('== %s (model %s, set %s) %.0f s\n' % (name, model, params, time.time() - t0) + '\n'.join(lines) + '\n')
        print(name, 'ok' if ok else 'NOT OK', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
