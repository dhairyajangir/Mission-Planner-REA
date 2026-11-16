"""AP_RAMTRON was an ap-lib gap (L1, named in a trace only). Its own source is wired directly into
AP_HAL_SITL's own storage backend (AP_HAL_SITL/Storage.h/.cpp: STORAGE_USE_FRAM is HAL_WITH_RAMTRON,
defined 1 for the SITL board itself in Tools/ardupilotwaf/boards.py - not gated behind a different
board class the way AP_Module/AP_HAL_Linux are), selected at runtime by --set-storage-fram-enabled 1,
and AP_HAL_SITL/SPIDevice.cpp even registers a stub "ramtron" SPI device name/bus/cs entry. Whether
that stub actually emulates a real FRAM chip, or just lets AP_RAMTRON::init() run and fail/succeed
some other way, is what this checks: does a Copter boot with FRAM storage enabled work, panic, or
silently fall back, and which AP_RAMTRON functions actually run.

    python3 sitl-ramtron-gdb.py <ardupilot tree> <out dir> <custom-gcs dir>
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
WORK = os.path.expanduser('~/cg-ramtron-gdb')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
FUNCTIONS = ['AP_RAMTRON::init', 'AP_RAMTRON::read', 'AP_RAMTRON::write', 'HALSITL::Storage::_storage_open', 'AP_HAL::panic']


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
    log = open(os.path.join(OUT, 'ramtron-gdb.txt'), 'w')
    proc = subprocess.Popen(['gdb', '-q', '-batch', '-x', gdb_script(), '--args', BIN, '-w', '--model', '+', '-I', '0', '-s', '1',
                             '--home', '%s,%s,%s,0' % HOME, '--set-storage-fram-enabled', '1'],
                            cwd=WORK, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    try:
        conn, _ = link.connect(5760, timeout=120.0)  # SITL blocks on accept() until a GCS connects
        time.sleep(5)
        print('[ramtron] arm: %r' % (flight.arm(conn),), flush=True)
        time.sleep(3)
        print('[ramtron] disarm: %r' % (flight.disarm(conn),), flush=True)
        time.sleep(3)
    except Exception as e:
        print('[ramtron] connect/arm failed: %r' % (e,), flush=True)
    subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
    try:
        proc.wait(60)
    except Exception:
        proc.kill()
    text = open(os.path.join(OUT, 'ramtron-gdb.txt'), errors='replace').read()
    hits = parse_hits(text)
    with open(os.path.join(OUT, 'ramtron-hits.txt'), 'w') as f:
        f.write('\n'.join('%s: %d hits' % (fn, n) for fn, n in hits) + '\n')
    print('[ramtron] %s' % hits, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
