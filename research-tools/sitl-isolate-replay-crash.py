"""Replays the exact first N commands of sitl-mavlink-command-sweep.py (same order, both COMMAND_LONG and COMMAND_INT, all parameters zero) against a fresh ArduPlane, then waits
`wait_s` with no further traffic, polling whether the process is still alive. Narrows whether the crash (panic in Location::get_alt_cm) needs more than one command, and how long after
the triggering command it takes to appear. Simulator only (WSL, pymavlink).

    python3 sitl-isolate-replay-crash.py <ardupilot tree> <out dir> [count] [wait_s]
"""
import json
import os
import subprocess
import sys
import time

from pymavlink import mavutil

TREE, OUT = sys.argv[1], sys.argv[2]
COUNT = int(sys.argv[3]) if len(sys.argv) > 3 else 16
WAIT = float(sys.argv[4]) if len(sys.argv) > 4 else 90.0
sys.path.insert(0, os.path.expanduser('~/custom-gcs'))
from customgcs import link  # noqa: E402

HOME = '-35.363261,149.165230,584,0'
WORK = os.path.expanduser('~/cg-replay')
BIN = os.path.join(TREE, 'build/sitl/bin/arduplane')
DEFAULTS = os.path.join(TREE, 'Tools/autotest/models/plane.parm')
# the first 16 commands sitl-mavlink-command-sweep.py sends to 'plane', in order (name, number); from command-sweep.csv
FIRST = [('MAV_CMD_ACCELCAL_VEHICLE_POS', 42429), ('MAV_CMD_AIRFRAME_CONFIGURATION', 2520), ('MAV_CMD_BATTERY_RESET', 42651), ('MAV_CMD_CAMERA_STOP_TRACKING', 2010),
         ('MAV_CMD_CAMERA_TRACK_POINT', 2004), ('MAV_CMD_CAMERA_TRACK_RECTANGLE', 2005), ('MAV_CMD_CAN_FORWARD', 32000), ('MAV_CMD_COMPONENT_ARM_DISARM', 400),
         ('MAV_CMD_CONTROL_HIGH_LATENCY', 2600), ('MAV_CMD_DEBUG_TRAP', 42700), ('MAV_CMD_DO_ACCEPT_MAG_CAL', 42425), ('MAV_CMD_DO_ADSB_OUT_IDENT', 10001),
         ('MAV_CMD_DO_AUTOTUNE_ENABLE', 212), ('MAV_CMD_DO_AUX_FUNCTION', 218), ('MAV_CMD_DO_CANCEL_MAG_CAL', 42426), ('MAV_CMD_DO_CHANGE_ALTITUDE', 186)]


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arduplane'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    proc = subprocess.Popen([BIN, '-w', '--model', 'plane', '-I', '0', '-s', '1', '--home', HOME, '--defaults', DEFAULTS], cwd=WORK,
                            stdout=open(os.path.join(WORK, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    sent, checks = [], []
    try:
        conn, _ = link.connect(5760, timeout=60.0)
        time.sleep(45)
        for name, number in FIRST[:COUNT]:
            conn.mav.command_long_send(conn.target_system, conn.target_component, number, 0, 0, 0, 0, 0, 0, 0, 0)
            ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=2.5)
            conn.mav.command_int_send(conn.target_system, conn.target_component, 0, number, 0, 0, 0, 0, 0, 0, 0, 0, 0)
            ack2 = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=2.5)
            sent.append({'name': name, 'long_ack': None if ack is None else ack.result, 'int_ack': None if ack2 is None else ack2.result, 'alive': proc.poll() is None})
            print('[replay] sent %s: long=%s int=%s alive=%s' % (name, sent[-1]['long_ack'], sent[-1]['int_ack'], sent[-1]['alive']), flush=True)
            if proc.poll() is not None:
                break
        begin = time.time()
        while time.time() - begin < WAIT and proc.poll() is None:
            time.sleep(10)
            checks.append({'uptime_after_replay_s': round(time.time() - begin, 1), 'alive': proc.poll() is None})
            print('[replay] +%.0f s after last command, alive=%s' % (checks[-1]['uptime_after_replay_s'], checks[-1]['alive']), flush=True)
    except Exception as e:
        sent.append({'exception': repr(e)})
    finally:
        subprocess.call(['pkill', '-x', 'arduplane'])
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
    log_tail = open(os.path.join(WORK, 'sitl.log'), errors='replace').read().splitlines()[-6:]
    json.dump({'sent': sent, 'checks': checks, 'log_tail': log_tail}, open(os.path.join(OUT, 'replay-result.json'), 'w'), indent=1)
    print('log tail:', log_tail)
    return 0


if __name__ == '__main__':
    sys.exit(main())
