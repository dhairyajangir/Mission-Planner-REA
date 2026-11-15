"""Confirms (or not) the hypothesis from sitl-copter-motor-failure.py: that Copter::thrust_loss_check never warned at 100 m because the commanded attitude exceeded the
function's own 15-degree reset threshold during the motor-out tumble (crash_check.cpp: "check for desired angle over 15 degrees ... thrust_loss_counter = 0; return;"). One gdb
breakpoint on Copter::thrust_loss_check's entry, printing copter.attitude_control->get_att_target_euler_rad() (roll/pitch, converted to degrees) every ~50th call (roughly twice
a second), over the same 100 m motor-failure scenario. Simulator only (WSL, gdb, the custom-gcs library).

    python3 sitl-motor-failure-angle-gdb.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
import math
import os
import re
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
WORK = os.path.expanduser('~/cg-motor-failure-angle')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')


def gdb_script():
    lines = [
        'set pagination off', 'set confirm off', 'handle SIGALRM SIGUSR1 SIGUSR2 SIGPIPE SIGURG nostop noprint pass',
        'set $cnt = 0',
        'break Copter::thrust_loss_check',
        'commands',
        'silent',
        'set $cnt = $cnt + 1',
        'if $cnt % 50 == 0',
        'printf "T=%d roll_deg=%f pitch_deg=%f\\n", $cnt, '
        'copter.attitude_control->get_att_target_euler_rad().x * 57.29578, copter.attitude_control->get_att_target_euler_rad().y * 57.29578',
        'end',
        'continue',
        'end',
        'run',
    ]
    path = os.path.join(WORK, 'gdb-commands.txt')
    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    return path


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arducopter'])
    subprocess.call(['pkill', '-x', 'gdb'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    log = open(os.path.join(OUT, 'motor-failure-angle-gdb.txt'), 'w')
    proc = subprocess.Popen(['gdb', '-q', '-batch', '-x', gdb_script(), '--args', BIN, '-w', '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    notes = []
    try:
        conn, _ = link.connect(5760, timeout=180.0)
        time.sleep(45)
        flight.set_mode(conn, 'GUIDED', table='copter')
        armed = flight.arm(conn, timeout=120.0)
        notes.append('arm: %s' % armed.detail)
        if armed.ok:
            conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, 100.0)
            ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
            notes.append('takeoff to 100 m ack %s' % (None if ack is None else ack.result))
            time.sleep(100)
            base = link.read_params(conn)
            bad = [r.name for r in params.write(conn, [params.Change('SIM_ENGINE_FAIL', base.get('SIM_ENGINE_FAIL'), 1.0)]) if not r.ok]
            notes.append('SIM_ENGINE_FAIL -> 1 (rejected %s)' % bad)
            time.sleep(15)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    text = open(os.path.join(OUT, 'motor-failure-angle-gdb.txt'), errors='replace').read()
    samples = [l for l in text.splitlines() if l.startswith('T=')]
    with open(os.path.join(OUT, 'motor-failure-angle-samples.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n\n%d samples\n' % len(samples))
        f.write('\n'.join(samples) + '\n')
    print('[motor-failure-angle] %d samples; last 5: %s' % (len(samples), samples[-5:]), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
