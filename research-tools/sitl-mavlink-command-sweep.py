"""Which MAV_CMD commands do the aerial autopilots handle, and what do they answer when a ground station sends them with all parameters zero? A sweep in a disarmed simulator.
Simulator only (WSL, pymavlink). Never use with a real vehicle or live link: some commands act on the vehicle.

    python3 sitl-mavlink-command-sweep.py <ardupilot tree> <out dir> [vehicle ...]       vehicles: copter, plane, quadplane, heli

The command list is read from the snapshot's source: every `MAV_CMD_*` name in a `case` label of libraries/GCS_MAVLink/GCS_Common.cpp and of the vehicle's own GCS_MAVLink_*.cpp (and,
for the mission-command side, ArduCopter/mode*.cpp and ArduPlane/commands_logic.cpp are not scanned: those are mission items, not immediate commands). Each name is mapped to its number with
pymavlink's dialect. Each command is sent twice to a freshly started vehicle, once as COMMAND_LONG and once as COMMAND_INT (frame MAV_FRAME_GLOBAL, x, y, z zero), one after the other with
a 2 s wait for the matching COMMAND_ACK; the result, the progress field and the vehicle's texts in that window are kept. Commands that would restart, shut down or flash the vehicle, or
terminate the flight, are listed but not sent. The vehicle is in whatever state the earlier commands left it in, so a result can depend on the order (the order is the command number).
Zero parameters are mostly invalid arguments, so "unsupported" (3) means the command is not handled at all, and "denied" or "failed" with zeros mean the handler exists but rejected the arguments.
"""
import csv
import os
import re
import subprocess
import sys
import time

from pymavlink import mavutil

TREE, OUT = sys.argv[1], sys.argv[2]
WANT = sys.argv[3:] or ['copter', 'plane', 'quadplane', 'heli']
sys.path.insert(0, os.path.expanduser('~/custom-gcs'))
from customgcs import link  # noqa: E402

HOME = '-35.363261,149.165230,584,0'
WORK = os.path.expanduser('~/cg-cmdsweep')
VEH = {'copter': ('arducopter', '+', None, 'ArduCopter/GCS_MAVLink_Copter.cpp'), 'plane': ('arduplane', 'plane', ['models/plane.parm'], 'ArduPlane/GCS_MAVLink_Plane.cpp'),
       'quadplane': ('arduplane', 'quadplane', ['default_params/quadplane.parm'], 'ArduPlane/GCS_MAVLink_Plane.cpp'),
       'heli': ('arducopter-heli', 'heli', None, 'ArduCopter/GCS_MAVLink_Copter.cpp')}
# ArduPlane/QuadPlane panicked at startup ("Should not be called on invalid location", AP_Common/Location.cpp:152) when started with --model and no --defaults; passing the frame's
# own default-parameter file (as every other script in this repo does) avoided it in testing. Kept here as a fix, not fully explained.
NOT_SENT = {'MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN': 'restarts or shuts down the vehicle', 'MAV_CMD_FLASH_BOOTLOADER': 'flashes the bootloader', 'MAV_CMD_DO_FLIGHTTERMINATION': 'terminates the flight',
            'MAV_CMD_DO_SEND_BANNER': 'prints the banner (harmless but noisy)', 'MAV_CMD_PREFLIGHT_STORAGE': 'writes or resets stored parameters with some arguments',
            'MAV_CMD_DO_CHANGE_ALTITUDE': 'with all-zero parameters this never acknowledges and stops the MAVLink command channel acknowledging anything sent after it on ArduPlane/QuadPlane '
                                          '(isolated and confirmed in sitl-isolate-replay-crash.py; the process does not crash until it is killed, at which point it panics in '
                                          'Location::get_alt_cm, AP_Common/Location.cpp:152, on an uninitialised (0,0,0) location)'}
RESULTS = {0: 'ACCEPTED', 1: 'TEMPORARILY_REJECTED', 2: 'DENIED', 3: 'UNSUPPORTED', 4: 'FAILED', 5: 'IN_PROGRESS', 6: 'CANCELLED', 7: 'COMMAND_LONG_ONLY', 8: 'COMMAND_INT_ONLY', 9: 'COMMAND_UNSUPPORTED_MAV_FRAME'}
NUM = {v.name: k for k, v in mavutil.mavlink.enums['MAV_CMD'].items()}


def source_commands(vehicle_file):
    names = set()
    for rel in ('libraries/GCS_MAVLink/GCS_Common.cpp', vehicle_file):
        text = open(os.path.join(TREE, rel), errors='replace').read()
        names |= set(re.findall(r'case\s+(MAV_CMD_[A-Z0-9_]+)\s*:', text))
    return sorted(names)


def wait_ack(conn, number, seconds):
    texts, end, ack = [], time.time() + seconds, None
    while time.time() < end:
        msg = conn.recv_match(type=['COMMAND_ACK', 'STATUSTEXT'], blocking=True, timeout=0.3)
        if msg is None:
            continue
        if msg.get_type() == 'COMMAND_ACK' and msg.command == number:
            ack = msg
            break
        if msg.get_type() == 'STATUSTEXT':
            texts.append(msg.text)
    return ack, texts


def sweep(name):
    binary, model, defaults, vfile = VEH[name]
    subprocess.call(['pkill', '-x', binary])
    time.sleep(1)
    work = os.path.join(WORK, name)
    subprocess.call(['rm', '-rf', work])
    os.makedirs(work)
    args = [os.path.join(TREE, 'build/sitl/bin', binary), '-w', '--model', model, '-I', '0', '-s', '1', '--home', HOME]
    if defaults:
        args += ['--defaults', ','.join(os.path.join(TREE, 'Tools/autotest', d) for d in defaults)]
    proc = subprocess.Popen(args, cwd=work, stdout=open(os.path.join(work, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    rows, boot_attempts = [], []
    try:
        conn = None
        for attempt in range(3):
            if proc.poll() is not None:                               # the simulator exited during start-up (seen: a SITL-only panic in Location::get_alt_cm
                boot_attempts.append('attempt %d: simulator exited during start-up (code %s)' % (attempt + 1, proc.poll()))  # called before any location was set)
                proc = subprocess.Popen(args, cwd=work, stdout=open(os.path.join(work, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)
            try:
                conn, _ = link.connect(5760, timeout=30.0)
            except Exception as e:
                boot_attempts.append('attempt %d: no heartbeat (%r)' % (attempt + 1, e))
                conn = None
                continue
            time.sleep(5)
            if proc.poll() is None:
                boot_attempts.append('attempt %d: ok' % (attempt + 1))
                break
            boot_attempts.append('attempt %d: exited right after connecting' % (attempt + 1))
            conn = None
        if conn is None:
            raise RuntimeError('simulator would not stay up after 3 attempts: %s' % boot_attempts)
        time.sleep(45)
        for cname in source_commands(vehicle_file=vfile):
            if cname not in NUM:
                rows.append([name, cname, '', 'not in the pymavlink dialect', '', '', ''])
                continue
            number = NUM[cname]
            if cname in NOT_SENT:
                rows.append([name, cname, number, 'NOT SENT: ' + NOT_SENT[cname], '', '', ''])
                continue
            out = [name, cname, number]
            for kind in ('LONG', 'INT'):
                if kind == 'LONG':
                    conn.mav.command_long_send(conn.target_system, conn.target_component, number, 0, 0, 0, 0, 0, 0, 0, 0)
                else:
                    conn.mav.command_int_send(conn.target_system, conn.target_component, 0, number, 0, 0, 0, 0, 0, 0, 0, 0, 0)
                ack, texts = wait_ack(conn, number, 2.5)
                out += [RESULTS.get(ack.result, str(ack.result)) if ack is not None else 'NO ACK', (' | '.join(texts))[:160]]
            rows.append(out)
        # the vehicle's state after the sweep
        hb = conn.recv_match(type='HEARTBEAT', blocking=True, timeout=5)
        rows.append([name, '(state after the sweep)', '', 'armed=%s custom_mode=%s' % (None if hb is None else bool(hb.base_mode & 128), None if hb is None else hb.custom_mode), '', '', ''])
    except Exception as e:
        rows.append([name, '(EXCEPTION)', '', repr(e), '', '', ''])
    rows.append([name, '(boot attempts)', '', '; '.join(boot_attempts), '', '', ''])
    subprocess.call(['pkill', '-x', binary])
    try:
        proc.wait(15)
    except Exception:
        proc.kill()
    return rows


def main():
    os.makedirs(OUT, exist_ok=True)
    allrows = []
    for name in WANT:
        rows = sweep(name)
        allrows += rows
        counts = {}
        for r in rows:
            counts[r[3]] = counts.get(r[3], 0) + 1
        print('[%s] %d commands; COMMAND_LONG results %s' % (name, len(rows), counts), flush=True)
    with open(os.path.join(OUT, 'command-sweep.csv'), 'w', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['vehicle', 'command', 'number', 'long_result_or_note', 'long_texts', 'int_result', 'int_texts'])
        for r in allrows:
            w.writerow(r[:7])
    return 0


if __name__ == '__main__':
    sys.exit(main())
