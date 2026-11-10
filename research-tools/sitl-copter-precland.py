"""Precision landing in a Copter simulator with the two simulated backends (PLND_TYPE 4 = SITL, 2 = IRLock, whose simulated sensor is AP_IRLock_SITL). Simulator only (WSL, gdb, the custom-gcs
library). ArduPilot's own autotest PrecisionLanding does the same; this run adds gdb entry evidence and the measured landing distance.

    python3 sitl-copter-precland.py <ardupilot tree> <out dir> <custom-gcs dir>

For each backend: a first start sets PLND_ENABLED, PLND_TYPE, an analog rangefinder and the simulator's landing-target parameters (SIM_PLD_*), the second start (no wipe, under gdb) places the
target 4 m north and 4 m west of the home position, takes off in GUIDED to 10 m, requests LAND and records where the vehicle disarmed.
"""
import json
import math
import os
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(35.363261))
WORK = os.path.expanduser('~/cg-precland')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
COMMON = ['AC_PrecLand::init', 'AC_PrecLand::update', 'AC_PrecLand::run_estimator', 'AC_PrecLand::run_output_prediction', 'AC_PrecLand::target_acquired',
          'AC_PrecLand::get_target_position_measurement_NED_m']
BACKENDS = {2: ('irlock', COMMON + ['AP_IRLock_SITL::init', 'AP_IRLock_SITL::update', 'AC_PrecLand_IRLock::init', 'AC_PrecLand_IRLock::update']),
            4: ('sitl', COMMON + ['AC_PrecLand_SITL::init', 'AC_PrecLand_SITL::update'])}


def start_plain(wipe):
    return subprocess.Popen([BIN] + (['-w'] if wipe else []) + ['--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                            stdout=open(os.path.join(WORK, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)


def start_gdb(functions, log_name):
    lines = ['set pagination off', 'set confirm off', 'handle SIGALRM SIGUSR1 SIGUSR2 SIGPIPE SIGURG nostop noprint pass']
    for fn in functions:
        lines += ['tbreak %s' % fn, 'commands', 'silent', 'printf "HIT %s\\n"' % fn, 'bt 4', 'continue', 'end']
    lines += ['run']
    script = os.path.join(WORK, 'gdb-commands.txt')
    with open(script, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    return subprocess.Popen(['gdb', '-q', '-batch', '-x', script, '--args', BIN, '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                            stdout=open(os.path.join(OUT, log_name), 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)


def metres(lat1, lon1, lat2, lon2):
    return math.hypot((lat2 - lat1) * M_LAT, (lon2 - lon1) * M_LON)


def position(conn, timeout=5.0):
    msg = conn.recv_match(type=['GLOBAL_POSITION_INT'], blocking=True, timeout=timeout)
    return None if msg is None else (msg.lat / 1e7, msg.lon / 1e7, msg.relative_alt / 1000.0)


def texts_until(conn, seconds, notes, prefix):
    end = time.time() + seconds
    while time.time() < end:
        msg = conn.recv_match(type=['STATUSTEXT'], blocking=True, timeout=0.5)
        if msg is not None:
            notes.append('%s vehicle: %s' % (prefix, msg.text))


def one(backend):
    name, functions = BACKENDS[backend]
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    notes, result, proc = [], {}, None
    try:
        proc = start_plain(True)
        conn, _ = link.connect(5760)
        time.sleep(15)
        base = link.read_params(conn)
        want = {'PLND_ENABLED': 1.0, 'PLND_TYPE': float(backend), 'RNGFND1_TYPE': 1.0, 'RNGFND1_PIN': 0.0, 'RNGFND1_SCALING': 10.0, 'RNGFND1_MIN': 0.0, 'RNGFND1_MAX': 40.0,
                'SIM_SONAR_SCALE': 12.0, 'SIM_PLD_ENABLE': 1.0, 'SIM_PLD_HEIGHT': 0.0, 'SIM_PLD_ALT_LMT': 15.0, 'SIM_PLD_DIST_LMT': 10.0}
        changes = [params.Change(n, base.get(n), v) for n, v in want.items()]
        bad = [r.name for r in params.write(conn, changes) if not r.ok]
        notes.append('set %s; rejected %s; absent at boot %s' % (want, bad, [n for n in want if n not in base]))
        time.sleep(2)
        proc.terminate()
        proc.wait(10)
        proc = start_gdb(functions, '%s-gdb.txt' % name)
        conn, _ = link.connect(5760, timeout=300.0)
        time.sleep(60)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 33, 200000, 0, 0, 0, 0, 0)       # SET_MESSAGE_INTERVAL: GLOBAL_POSITION_INT at 5 Hz (run 1 received none)
        tlat, tlon = HOME[0] + 4 / M_LAT, HOME[1] - 4 / M_LON
        bad = [r.name for r in params.write(conn, [params.Change('SIM_PLD_LAT', 0.0, tlat), params.Change('SIM_PLD_LON', 0.0, tlon)]) if not r.ok]
        notes.append('target %.7f %.7f (4 m north, 4 m west of home); rejected %s' % (tlat, tlon, bad))
        notes.append('GUIDED: %s' % flight.set_mode(conn, 'GUIDED').detail)
        armed = flight.arm(conn, timeout=150.0)
        notes.append('arm: %s' % armed.detail)
        if armed.ok:
            conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, 10.0)
            begin = time.time()
            while time.time() - begin < 40.0:
                p = position(conn)
                if p and p[2] >= 9.0:
                    break
            notes.append('climb: %s after %.0f s' % (p, time.time() - begin))
            notes.append('LAND: %s' % flight.set_mode(conn, 'LAND').detail)
            was = None
            begin, last = time.time(), None
            while time.time() - begin < 120.0:
                msg = conn.recv_match(type=['HEARTBEAT', 'GLOBAL_POSITION_INT', 'STATUSTEXT'], blocking=True, timeout=1)
                if msg is None:
                    continue
                t = msg.get_type()
                if t == 'GLOBAL_POSITION_INT':
                    last = (msg.lat / 1e7, msg.lon / 1e7, msg.relative_alt / 1000.0)
                elif t == 'STATUSTEXT':
                    notes.append('t=%5.1f vehicle: %s' % (time.time() - begin, msg.text))
                elif msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                    armed_now = flight.is_armed(msg)
                    if was and not armed_now:
                        notes.append('t=%5.1f disarmed' % (time.time() - begin))
                        break
                    was = armed_now
            if last:
                result['landed_at'] = last
                result['distance_from_target_m'] = round(metres(last[0], last[1], tlat, tlon), 2)
                result['distance_from_home_m'] = round(metres(last[0], last[1], HOME[0], HOME[1]), 2)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        if proc:
            try:
                proc.wait(120)
            except Exception:
                proc.kill()
    text = open(os.path.join(OUT, '%s-gdb.txt' % name), errors='replace').read() if os.path.exists(os.path.join(OUT, '%s-gdb.txt' % name)) else ''
    hit = [fn for fn in functions if 'HIT %s' % fn in text]
    result.update({'backend': backend, 'name': name, 'notes': notes, 'hit': hit, 'not_reached': [fn for fn in functions if fn not in hit]})
    with open(os.path.join(OUT, '%s-result.json' % name), 'w') as f:
        json.dump(result, f, indent=1)
    print('[%s] hit %d of %d; landed %s m from target (%s m from home); not reached %s' % (name, len(hit), len(functions), result.get('distance_from_target_m'),
                                                                                        result.get('distance_from_home_m'), result['not_reached']), flush=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    for backend in (2, 4):
        one(backend)
    return 0


if __name__ == '__main__':
    sys.exit(main())
