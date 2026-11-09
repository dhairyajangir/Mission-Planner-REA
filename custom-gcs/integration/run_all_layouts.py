"""Run the prototype's motor test (customgcs.link.run_motor_test) against a disposable Copter simulator for every generated frame class/type layout.

Simulator only (WSL, ArduPilot SITL, pymavlink). For each 'class:type' key of customgcs/data/matrix_layouts.json (default entries are skipped) the script starts
arducopter with a physics model that fits the class, sets FRAME_CLASS and FRAME_TYPE, restarts without wiping, and lets customgcs plan and run the motor test.
Each frame writes <out>/layout-<class>-<type>.txt; the line 'RESULT' says how many planned steps moved exactly the expected outputs.

    python3 run_all_layouts.py <ardupilot tree> <out dir> <worker index> <worker count>

Workers split the keys and use simulator instances equal to the worker index (tcp 5760 + 10 * index), so they can run side by side.
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from customgcs import link, motors  # noqa: E402

TREE, OUT, WORKER, WORKERS = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
PLANE = os.environ.get('CG_PLANE') == '1'      # CG_PLANE=1: QuadPlane (arduplane, Q_FRAME_*), only the NYT types 16 and 17 that the Copter build does not contain
BINARY, PREFIX, TAG = ('arduplane', 'Q_', 'quadplane-') if PLANE else ('arducopter', '', '')
MODEL = {1: '+', 2: 'hexa', 3: 'octa', 4: 'octa-quad', 5: 'y6', 7: 'tri', 12: 'dodeca-hexa', 14: 'deca'}
PORT = 5760 + 10 * WORKER
WORK = os.path.expanduser('~/cg-layouts/%sw%d' % ('plane-' if PLANE else '', WORKER))
HOME = '-35.363261,149.165230,584,0'


def start(model, wipe):
    log = open(os.path.join(WORK, 'sitl.log'), 'a')
    return subprocess.Popen([os.path.join(TREE, 'build/sitl/bin/' + BINARY)] + (['-w'] if wipe else []) + ['--model', ('quadplane' if PLANE else model), '-I', str(WORKER), '-s', '1', '--home', HOME],
                            cwd=WORK, stdout=log, stderr=subprocess.STDOUT)


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


def one(cls, typ):
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    proc = start(MODEL[cls], wipe=True)
    try:
        conn, _ = link.connect(PORT)
        time.sleep(15)
        set_param(conn, PREFIX + 'FRAME_CLASS', cls)
        set_param(conn, PREFIX + 'FRAME_TYPE', typ)
        time.sleep(2)
    finally:
        stop(proc)
    proc = start(MODEL[cls], wipe=False)
    try:
        conn, mav_type = link.connect(PORT)
        params = link.read_params(conn)
        info = link.detect(params, mav_type)
        want_kind = 'quadplane' if PLANE else 'copter'
        lines = ['vehicle: %s, FRAME_CLASS %s, FRAME_TYPE %s' % (info.kind, info.frame_class, info.frame_type)]
        if info.kind != want_kind or (info.frame_class, info.frame_type) != (cls, typ):
            lines.append('RESULT wrong frame read back: wanted %d/%d' % (cls, typ))
            return lines, False
        results = link.run_motor_test(conn, info, params, 10.0)
        for r in results:
            lines.append('%-40s expected=%-14s moved=%-14s %s %s' % (r.label, r.expected, r.moved, 'OK' if r.ok else 'MISMATCH', r.note))
        good = sum(1 for r in results if r.ok)
        lines.append('RESULT %d of %d steps matched' % (good, len(results)))
        return lines, good == len(results)
    finally:
        stop(proc)


def main():
    os.makedirs(OUT, exist_ok=True)
    keys = sorted((int(k.split(':')[0]), int(k.split(':')[1])) for k in motors.layouts() if not k.endswith(':default') and int(k.split(':')[0]) in MODEL)
    if PLANE:
        keys = [(1, 16), (1, 17)]
    mine = [k for i, k in enumerate(keys) if i % WORKERS == WORKER]
    for cls, typ in mine:
        name = os.path.join(OUT, TAG + 'layout-%d-%d.txt' % (cls, typ))
        if os.path.exists(name):
            continue
        t0 = time.time()
        try:
            lines, ok = one(cls, typ)
        except Exception as e:                                           # keep the failure as the record
            lines, ok = ['RESULT exception: %r' % (e,)], False
        with open(name, 'w') as f:
            f.write('== class %d type %d (model %s) %.0f s\n' % (cls, typ, MODEL[cls], time.time() - t0) + '\n'.join(lines) + '\n')
        print(cls, typ, 'ok' if ok else 'NOT OK', lines[-1], flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
