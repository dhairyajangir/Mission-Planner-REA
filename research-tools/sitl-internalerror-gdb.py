"""AP_InternalError was an ap-lib gap (L1, named in a trace only). Its own source makes two things checkable
without any actual fault: AP_INTERNALERROR_ENABLED defaults to 1 for every board (AP_InternalError_config.h),
and its one external consumer relevant to arming, AP_Arming::system_checks() (AP_Arming.cpp), checks
AP::internalerror().errors() != 0 on every prearm check pass and would refuse to arm with "Internal errors
0x%x l:%u %s" if any bit were set. A normal arm attempt already runs system_checks(), so this confirms both
AP_InternalError::error() (never hit in ordinary operation - no false positives) and the prearm consumer that
reads it (hit on every check pass) are live, reachable code in this build.

    python3 sitl-internalerror-gdb.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
import os
import re
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import link, flight  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
WORK = os.path.expanduser('~/cg-internalerror-gdb')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
FUNCTIONS = ['AP_InternalError::error', 'AP_Arming::system_checks']


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
    log = open(os.path.join(OUT, 'internalerror-gdb.txt'), 'w')
    proc = subprocess.Popen(['gdb', '-q', '-batch', '-x', gdb_script(), '--args', BIN, '-w', '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME],
                            cwd=WORK, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    try:
        conn, _ = link.connect(5760, timeout=120.0)  # SITL blocks on accept() until a GCS connects
        time.sleep(10)
        print('[internalerror] arm: %r' % (flight.arm(conn),), flush=True)
        time.sleep(3)
        print('[internalerror] disarm: %r' % (flight.disarm(conn),), flush=True)
        time.sleep(3)
    except Exception as e:
        print('[internalerror] connect/arm failed: %r' % (e,), flush=True)
    subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
    try:
        proc.wait(60)
    except Exception:
        proc.kill()
    text = open(os.path.join(OUT, 'internalerror-gdb.txt'), errors='replace').read()
    hits = parse_hits(text)
    with open(os.path.join(OUT, 'internalerror-hits.txt'), 'w') as f:
        f.write('\n'.join('%s: %d hits' % (fn, n) for fn, n in hits) + '\n')
    print('[internalerror] %s' % hits, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
