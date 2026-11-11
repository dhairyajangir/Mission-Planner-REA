"""AP_PiccoloCAN was the one remaining library from the original breakpoint sweep's "present in a binary but never entered" pair (the other, AP_RCTelemetry, was resolved earlier
by enabling its CRSF backend). PiccoloCAN needs no hardware either: SITL's own CAN simulation defaults to a UDP-multicast transport (SIM_CAN_TYPE1, no vcan/SocketCAN or root
needed), so enabling a CAN driver and pointing it at the PiccoloCAN protocol should be enough to allocate and run the backend, the same pattern as AP_HAL_SITL/AP_Vehicle above.
CAN_P1_DRIVER (enable physical CAN port 1) and CAN_D1_PROTOCOL (4 = PiccoloCAN) are both RebootRequired, the same two-stage boot used throughout this project for enable-flag
parameters. Simulator only (WSL, gdb, the custom-gcs library for the one connect).

    python3 sitl-piccolocan-gdb.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
import os
import re
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import link, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
WORK = os.path.expanduser('~/cg-piccolocan-gdb')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
FUNCTIONS = ['AP_PiccoloCAN::init', 'AP_PiccoloCAN::update']


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


def start(wipe, under_gdb):
    args = [BIN] + (['-w'] if wipe else []) + ['--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME]
    if not under_gdb:
        return subprocess.Popen(args, cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)
    log = open(os.path.join(OUT, 'piccolocan-gdb.txt'), 'w')
    return subprocess.Popen(['gdb', '-q', '-batch', '-x', gdb_script(), '--args'] + args, cwd=WORK, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arducopter'])
    subprocess.call(['pkill', '-x', 'gdb'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    notes, proc = [], start(True, False)
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        time.sleep(45)
        base = link.read_params(conn)
        changes = [params.Change('CAN_P1_DRIVER', base.get('CAN_P1_DRIVER'), 1.0), params.Change('CAN_D1_PROTOCOL', base.get('CAN_D1_PROTOCOL'), 4.0)]
        bad = [r.name for r in params.write(conn, changes) if not r.ok]
        notes.append('CAN_P1_DRIVER -> 1, CAN_D1_PROTOCOL -> 4 (PiccoloCAN) (rejected %s); restarting under gdb' % bad)
        time.sleep(2)
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
        proc = start(False, True)
        conn, _ = link.connect(5760, timeout=180.0)
        after = link.read_params(conn)
        notes.append('after restart under gdb: CAN_P1_DRIVER=%s CAN_D1_PROTOCOL=%s' % (after.get('CAN_P1_DRIVER'), after.get('CAN_D1_PROTOCOL')))
        time.sleep(30)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    text = open(os.path.join(OUT, 'piccolocan-gdb.txt'), errors='replace').read()
    hits = parse_hits(text)
    with open(os.path.join(OUT, 'piccolocan-hits.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n\n' + '\n'.join('%s: %d hits' % (fn, n) for fn, n in hits) + '\n')
    print('[piccolocan] %s' % hits, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
