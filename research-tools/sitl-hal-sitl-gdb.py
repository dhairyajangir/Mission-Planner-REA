"""AP_HAL_SITL itself (the HAL layer every simulator run in this repository uses) has no evidence row of its own, even though it is obviously exercised by every one of this
project's SITL flights. Rather than just assert that, one minimal gdb check: breakpoints on HALSITL::SITL_State::_sitl_setup() (one-time start-up) and
HALSITL::SITL_State::_fdm_input_local() (the per-loop step that feeds the flight-dynamics model into the autopilot; _fdm_input_step() just calls it and, going by a first attempt
that connected nothing and saw 0 hits on both, SITL blocks at accept() on SERIAL0 until a GCS connects, so a bare MAVLink TCP connect is needed before the main loop ticks at all)
over a plain Copter boot, no mission. Simulator only (WSL, gdb, the custom-gcs library for the one connect).

    python3 sitl-hal-sitl-gdb.py <ardupilot tree> <out dir> <custom-gcs dir>
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
WORK = os.path.expanduser('~/cg-hal-sitl-gdb')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
FUNCTIONS = ['HALSITL::SITL_State::_sitl_setup', 'HALSITL::SITL_State::_fdm_input_local']


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
    log = open(os.path.join(OUT, 'hal-sitl-gdb.txt'), 'w')
    proc = subprocess.Popen(['gdb', '-q', '-batch', '-x', gdb_script(), '--args', BIN, '-w', '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME],
                            cwd=WORK, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    try:
        conn, _ = link.connect(5760, timeout=120.0)  # SITL blocks on accept() until a GCS connects; nothing further is sent, the connect alone lets the main loop start
        time.sleep(20)
    except Exception as e:
        print('[hal-sitl] connect failed: %r' % (e,), flush=True)
    subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
    try:
        proc.wait(60)
    except Exception:
        proc.kill()
    text = open(os.path.join(OUT, 'hal-sitl-gdb.txt'), errors='replace').read()
    hits = parse_hits(text)
    with open(os.path.join(OUT, 'hal-sitl-hits.txt'), 'w') as f:
        f.write('\n'.join('%s: %d hits' % (fn, n) for fn, n in hits) + '\n')
    print('[hal-sitl] %s' % hits, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
