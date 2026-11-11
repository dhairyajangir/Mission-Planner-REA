"""Whether AP_RCTelemetry/AP_CRSF_Telem (ArduPilot-Aerial-Library-Execution-Trace.md: "present in a binary but never entered") can be reached in the simulator without
any hardware, using ArduPilot's own built-in SITL CRSF device (libraries/SITL/SIM_CRSF.*, its header comment is the worked example this script follows): a UART configured
as a generic RC-input port (`--serial5=sim:crsf`, SERIAL5_PROTOCOL 23) and the simulator's own CRSF device writes real CRSF frames (VTX_FRAME/VTX_TELEM/VTX_UNKNOWN,
0xC8-headers) into that port every 400 ms, which AP_RCProtocol_CRSF should decode and hand to AP_CRSF_Telem::process_frame. SERIAL5_PROTOCOL is read once at boot
(AP_SerialManager::init), so it needs the same two-stage reboot as the enable-flag parameters elsewhere in this project, even though it is not an ENABLE-flag parameter itself.
Simulator only (WSL, gdb, the custom-gcs library).

    python3 sitl-crsf-telemetry-gdb.py <ardupilot tree> <out dir> <custom-gcs dir>
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
WORK = os.path.expanduser('~/cg-crsf-telem')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
EXTRA = ['--serial5=sim:crsf']
FUNCTIONS = ['AP_CRSF_Telem::AP_CRSF_Telem', 'AP_CRSF_Telem::get_singleton', 'AP_RCProtocol_CRSF::_process_byte', 'AP_RCProtocol_CRSF::decode_crsf_packet']


def start(wipe, under_gdb):
    args = [BIN] + (['-w'] if wipe else []) + ['--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME] + EXTRA
    if not under_gdb:
        return subprocess.Popen(args, cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)
    lines = ['set pagination off', 'set confirm off', 'handle SIGALRM SIGUSR1 SIGUSR2 SIGPIPE SIGURG nostop noprint pass']
    for fn in FUNCTIONS:
        lines += ['break %s' % fn, 'commands', 'silent', 'continue', 'end']
    lines += ['run', 'info breakpoints']
    gdb_path = os.path.join(WORK, 'gdb-commands.txt')
    with open(gdb_path, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    log = open(os.path.join(OUT, 'crsf-telemetry-gdb.txt'), 'w')
    return subprocess.Popen(['gdb', '-q', '-batch', '-x', gdb_path, '--args'] + args, cwd=WORK, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)


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
    subprocess.call(['pkill', '-x', 'gdb'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    notes = []
    proc = start(True, False)
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        time.sleep(45)
        base = link.read_params(conn)
        bad = [r.name for r in params.write(conn, [params.Change('SERIAL5_PROTOCOL', base.get('SERIAL5_PROTOCOL'), 23.0)]) if not r.ok]
        notes.append('SERIAL5_PROTOCOL was %s, set to 23 (RCIN, rejected %s); restarting under gdb' % (base.get('SERIAL5_PROTOCOL'), bad))
        time.sleep(2)
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
        proc = start(False, True)
        conn, _ = link.connect(5760, timeout=180.0)
        after = link.read_params(conn)
        notes.append('after restart under gdb, SERIAL5_PROTOCOL=%s' % after.get('SERIAL5_PROTOCOL'))
        # AP_CRSF_Telem::get_singleton() only allocates while disarmed (!hal.util->get_soft_armed()), so stay disarmed for this test.
        # The SITL CRSF device writes a frame every 400 ms; give the decoder and the telemetry allocation time to run.
        time.sleep(50)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    text = open(os.path.join(OUT, 'crsf-telemetry-gdb.txt'), errors='replace').read()
    hits = parse_hits(text)
    with open(os.path.join(OUT, 'crsf-telemetry-hits.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n\n' + '\n'.join('%s: %d hits' % (fn, n) for fn, n in hits) + '\n')
    print('[crsf-telemetry] %s' % hits, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
