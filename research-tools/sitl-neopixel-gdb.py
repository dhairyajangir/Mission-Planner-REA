"""AP_SerialLED (confirmed present with symbols but never entered by the original breakpoint sweep: "no serial LED configured") needs no hardware either: just a NeoPixel backend
enabled via NTF_LED_TYPES bit 8 (256) and one SERVO output assigned the k_LED_neopixel1 function (120, SRV_Channel.h) - SITL happily bit-bangs the WS2812 protocol out to an output
channel nobody reads, the same spirit as AP_PiccoloCAN writing CAN frames nobody answers. NTF_LED_TYPES's driver list is built once at AP_Notify::init(), so this needs the usual
two-stage reboot. Simulator only (WSL, gdb, the custom-gcs library).

    python3 sitl-neopixel-gdb.py <ardupilot tree> <out dir> <custom-gcs dir>
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
WORK = os.path.expanduser('~/cg-neopixel-gdb')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
FUNCTIONS = ['SerialLED::init', 'SerialLED::hw_set_rgb', 'NeoPixel::NeoPixel']


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
    log = open(os.path.join(OUT, 'neopixel-gdb.txt'), 'w')
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
        new_led_types = float(int(base.get('NTF_LED_TYPES', 0)) | 256)  # OR in bit 8 (NeoPixel), keep the existing default bits
        changes = [params.Change('NTF_LED_TYPES', base.get('NTF_LED_TYPES'), new_led_types), params.Change('SERVO9_FUNCTION', base.get('SERVO9_FUNCTION'), 120.0)]
        bad = [r.name for r in params.write(conn, changes) if not r.ok]
        notes.append('NTF_LED_TYPES -> %s (was %s), SERVO9_FUNCTION -> 120 (k_LED_neopixel1) (rejected %s); restarting under gdb' % (new_led_types, base.get('NTF_LED_TYPES'), bad))
        time.sleep(2)
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
        proc = start(False, True)
        conn, _ = link.connect(5760, timeout=180.0)
        after = link.read_params(conn)
        notes.append('after restart under gdb: NTF_LED_TYPES=%s SERVO9_FUNCTION=%s' % (after.get('NTF_LED_TYPES'), after.get('SERVO9_FUNCTION')))
        time.sleep(30)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    text = open(os.path.join(OUT, 'neopixel-gdb.txt'), errors='replace').read()
    hits = parse_hits(text)
    with open(os.path.join(OUT, 'neopixel-hits.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n\n' + '\n'.join('%s: %d hits' % (fn, n) for fn, n in hits) + '\n')
    print('[neopixel] %s' % hits, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
