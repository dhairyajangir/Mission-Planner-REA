"""AP_Vehicle itself (the common base class every ArduPilot vehicle type inherits from, exercised by every single flight in this repository) has no evidence row of its own. One
minimal gdb check, same lesson as sitl-hal-sitl-gdb.py (a bare MAVLink TCP connect is needed before SITL's main loop starts, it blocks at accept() on SERIAL0 until then): breakpoints
on AP_Vehicle::setup() (one-time start-up, calls the vehicle's own init then the common one) and AP_Vehicle::loop() (the scheduler's main-loop entry point) over a plain Copter boot,
no mission. Simulator only (WSL, gdb, the custom-gcs library for the one connect).

    python3 sitl-ap-vehicle-gdb.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
import os
import re
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import link  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
WORK = os.path.expanduser('~/cg-ap-vehicle-gdb')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
FUNCTIONS = ['AP_Vehicle::setup', 'AP_Vehicle::loop', 'AP_Vehicle::one_Hz_update']


def gdb_script():
    lines = ['set pagination off', 'set confirm off', 'handle SIGALRM SIGUSR1 SIGUSR2 SIGPIPE SIGURG nostop noprint pass']
    for fn in FUNCTIONS:
        lines += ['break %s' % fn, 'commands', 'silent', 'continue', 'end']
    lines += ['run', 'info breakpoints']
    path = os.path.join(WORK, 'gdb-commands.txt')
    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    return path


def parse_hits(text):
    table = text[text.rfind('Num     Type'):] if 'Num     Type' in text else ''
    out, current = [], None
    for line in table.splitlines():
        m = re.match(r'\s*\d+\s+breakpoint\s+keep\s+\w\s+0x[0-9a-f]+\s+(?:in\s+(.+?)\s+at\s|<(.+)>\s*$)', line)
        if m:
            current = [re.sub(r'\(.*$', '', m.group(1) or m.group(2)), 0]
            out.append(current)
            continue
        h = re.match(r'\s*breakpoint already hit (\d+) time', line)
        if h and current is not None:
            current[1] = int(h.group(1))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arducopter'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    log = open(os.path.join(OUT, 'ap-vehicle-gdb.txt'), 'w')
    proc = subprocess.Popen(['gdb', '-q', '-batch', '-x', gdb_script(), '--args', BIN, '-w', '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME],
                            cwd=WORK, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    try:
        conn, _ = link.connect(5760, timeout=120.0)  # SITL blocks on accept() until a GCS connects; see sitl-hal-sitl-gdb.py
        time.sleep(65)  # one_Hz_update needs at least a few seconds of ticking to be worth checking
    except Exception as e:
        print('[ap-vehicle] connect failed: %r' % (e,), flush=True)
    subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
    try:
        proc.wait(60)
    except Exception:
        proc.kill()
    text = open(os.path.join(OUT, 'ap-vehicle-gdb.txt'), errors='replace').read()
    hits = parse_hits(text)
    with open(os.path.join(OUT, 'ap-vehicle-hits.txt'), 'w') as f:
        f.write('\n'.join('%s: %d hits' % (fn, n) for fn, n in hits) + '\n')
    print('[ap-vehicle] %s' % hits, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
