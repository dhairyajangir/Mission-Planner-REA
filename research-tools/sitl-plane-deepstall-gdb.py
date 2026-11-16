"""The standalone PID library (libraries/PID) was an unresolved ap-lib gap, and its only caller anywhere in the tree is AP_Landing_Deepstall (ArduPlane's deepstall landing
type, LAND_TYPE=1): a steep, intentionally-stalled, full-rudder spiral descent used instead of a normal glide-slope landing. HAL_LANDING_DEEPSTALL_ENABLED is
(HAL_PROGRAM_SIZE_LIMIT_KB > 1024) (AP_Landing_config.h), true on SITL, so it should be compiled in. LAND_TYPE is an AP_PARAM_FLAG_ENABLE parameter (the usual
two-stage-reboot pattern elsewhere in this project) that selects it. This flies the same takeoff/waypoints/LAND mission used elsewhere for Plane, with LAND_TYPE=1 and a
light steady crosswind (deepstall needs a wind estimate to plan its approach), and watches the deepstall functions and the PID instance they use with gdb.

    python3 sitl-plane-deepstall-gdb.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
import math
import os
import re
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import link, flight, mission, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
WORK = os.path.expanduser('~/cg-deepstall-gdb')
BIN = os.path.join(TREE, 'build/sitl/bin/arduplane')
TABLE = 'plane'
FUNCTIONS = ['AP_Landing_Deepstall::do_land', 'AP_Landing_Deepstall::build_approach_path', 'AP_Landing_Deepstall::update_steering',
             'AP_Landing_Deepstall::verify_land', 'AP_Landing_Deepstall::override_servos', 'PID::get_pid']
M_PER_DEG_LAT = 111320.0
LEG_DEG = 300.0 / M_PER_DEG_LAT
LEG_DEG_LON = 300.0 / (M_PER_DEG_LAT * math.cos(math.radians(HOME[0])))
CRUISE_ALT_M = 70.0


def route():
    a = (HOME[0] + LEG_DEG, HOME[1])
    b = (a[0], a[1] + LEG_DEG_LON)
    items = [mission.Item(0, 0, 16, 0, 1, 0.0, 0.0, 0.0, 0.0, HOME[0], HOME[1], HOME[2]),
             mission.Item(1, 3, 22, 0, 1, 15.0, 0.0, 0.0, 0.0, 0.0, 0.0, CRUISE_ALT_M),
             mission.Item(2, 3, 16, 0, 1, 0.0, 0.0, 0.0, 0.0, a[0], a[1], CRUISE_ALT_M),
             mission.Item(3, 3, 16, 0, 1, 0.0, 0.0, 0.0, 0.0, b[0], b[1], CRUISE_ALT_M),
             mission.Item(4, 3, 21, 0, 1, 0.0, 0.0, 0.0, 0.0, HOME[0], HOME[1], 0.0)]
    return items


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
    args = [BIN] + (['-w'] if wipe else []) + ['--model', 'plane', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME]
    if not under_gdb:
        return subprocess.Popen(args, cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)
    log = open(os.path.join(OUT, 'deepstall-gdb.txt'), 'w')
    return subprocess.Popen(['gdb', '-q', '-batch', '-x', gdb_script(), '--args'] + args, cwd=WORK, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arduplane'])
    subprocess.call(['pkill', '-x', 'gdb'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    notes, proc = [], start(True, False)
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        time.sleep(20)
        base = link.read_params(conn)
        changes = [params.Change('LAND_TYPE', base.get('LAND_TYPE'), 1.0), params.Change('SIM_WIND_SPD', base.get('SIM_WIND_SPD'), 4.0),
                   params.Change('SIM_WIND_DIR', base.get('SIM_WIND_DIR'), 90.0)]
        bad = [r.name for r in params.write(conn, changes) if not r.ok]
        notes.append('LAND_TYPE -> 1 (deepstall), SIM_WIND_SPD -> 4, SIM_WIND_DIR -> 90 (rejected %s); restarting under gdb' % bad)
        time.sleep(2)
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
        proc = start(False, True)
        conn, _ = link.connect(5760, timeout=180.0)
        after = link.read_params(conn)
        notes.append('after restart under gdb: LAND_TYPE=%s' % after.get('LAND_TYPE'))
        time.sleep(20)

        items = route()
        up = mission.upload(conn, items)
        notes.append('mission upload ack %s' % up)
        flight.set_mode(conn, 'MANUAL', table=TABLE)
        armed = flight.arm(conn, timeout=120.0)
        notes.append('armed: %r' % (armed,))
        auto = flight.set_mode(conn, 'AUTO', table=TABLE)
        retry = time.time() + 60.0
        while not auto.ok and time.time() < retry:
            time.sleep(3)
            auto = flight.set_mode(conn, 'AUTO', table=TABLE)
        notes.append('AUTO: %r' % (auto,))

        start_t = time.time()
        last_hb = None
        while time.time() - start_t < 300.0:
            msg = conn.recv_match(type=['STATUSTEXT', 'HEARTBEAT'], blocking=True, timeout=1)
            if msg is None:
                continue
            if msg.get_type() == 'STATUSTEXT':
                notes.append('t=%5.1f s vehicle: %s' % (time.time() - start_t, msg.text))
            elif msg.get_type() == 'HEARTBEAT' and msg.get_srcComponent() == 1:
                if last_hb is None or last_hb.custom_mode != msg.custom_mode or flight.is_armed(last_hb) != flight.is_armed(msg):
                    notes.append('t=%5.1f s heartbeat: %s, mode %s' % (time.time() - start_t, 'ARMED' if flight.is_armed(msg) else 'DISARMED', flight.mode_name(msg.custom_mode, TABLE)))
                last_hb = msg
                if last_hb is not None and not flight.is_armed(last_hb) and time.time() - start_t > 30:
                    notes.append('disarmed, stopping watch')
                    break
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arduplane'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    text = open(os.path.join(OUT, 'deepstall-gdb.txt'), errors='replace').read()
    hits = parse_hits(text)
    with open(os.path.join(OUT, 'deepstall-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n\n' + '\n'.join('%s: %d hits' % (fn, n) for fn, n in hits) + '\n')
    print('[deepstall] %s' % hits, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
