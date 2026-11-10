"""Isolates which single command crashes ArduPlane/QuadPlane in sitl-mavlink-command-sweep.py: MAV_CMD_DO_CHANGE_ALTITUDE (186) was the first command after which every later command got no
reply. Simulator only (WSL, pymavlink). Boots one fresh simulator per case and sends exactly one command (COMMAND_LONG or COMMAND_INT, all parameters zero, frame MAV_FRAME_GLOBAL for the
INT form), then checks whether the simulator process is still alive and whether a COMMAND_ACK came back.

    python3 sitl-isolate-change-altitude-crash.py <ardupilot tree> <out dir>
"""
import json
import os
import subprocess
import sys
import time

from pymavlink import mavutil

TREE, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.expanduser('~/custom-gcs'))
from customgcs import link  # noqa: E402

HOME = '-35.363261,149.165230,584,0'
WORK = os.path.expanduser('~/cg-isolate')
BIN = os.path.join(TREE, 'build/sitl/bin/arduplane')
DEFAULTS = os.path.join(TREE, 'Tools/autotest/models/plane.parm')
CASES = [('DO_CHANGE_ALTITUDE', 186, 'LONG'), ('DO_CHANGE_ALTITUDE', 186, 'INT'), ('DO_CHANGE_SPEED', 178, 'LONG'), ('DO_CHANGE_SPEED', 178, 'INT'), ('nothing (control)', None, None)]


def one(name, number, kind):
    subprocess.call(['pkill', '-x', 'arduplane'])
    time.sleep(1)
    work = os.path.join(WORK, '%s-%s' % (name.replace(' ', '_').replace('(', '').replace(')', ''), kind or 'none'))
    subprocess.call(['rm', '-rf', work])
    os.makedirs(work)
    proc = subprocess.Popen([BIN, '-w', '--model', 'plane', '-I', '0', '-s', '1', '--home', HOME, '--defaults', DEFAULTS], cwd=work,
                            stdout=open(os.path.join(work, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    result = {'case': name, 'number': number, 'kind': kind}
    try:
        conn, _ = link.connect(5760, timeout=60.0)
        time.sleep(45)
        result['alive_before_send'] = proc.poll() is None
        if number is not None:
            if kind == 'LONG':
                conn.mav.command_long_send(conn.target_system, conn.target_component, number, 0, 0, 0, 0, 0, 0, 0, 0)
            else:
                conn.mav.command_int_send(conn.target_system, conn.target_component, 0, number, 0, 0, 0, 0, 0, 0, 0, 0, 0)
            ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
            result['ack'] = None if ack is None else ack.result
        time.sleep(2)
        result['alive_after_send'] = proc.poll() is None
    except Exception as e:
        result['exception'] = repr(e)
    finally:
        subprocess.call(['pkill', '-x', 'arduplane'])
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
    log_tail = open(os.path.join(work, 'sitl.log'), errors='replace').read().splitlines()[-4:]
    result['log_tail'] = log_tail
    print('[%s %s] alive_before=%s alive_after=%s ack=%s tail=%s' % (name, kind, result.get('alive_before_send'), result.get('alive_after_send'), result.get('ack'), log_tail[-1:]), flush=True)
    return result


def main():
    os.makedirs(OUT, exist_ok=True)
    results = [one(name, number, kind) for name, number, kind in CASES]
    json.dump(results, open(os.path.join(OUT, 'isolate-results.json'), 'w'), indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
