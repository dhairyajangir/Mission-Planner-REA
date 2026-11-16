"""Fault injection follow-up to ledger:copter-precision-landing (confirmed clean: landed 0.98 m from target, both backends, no fault). AC_PrecLand.cpp has documented target-loss
handling: LANDING_TARGET_TIMEOUT_MS (2000) before target_acquired() goes false and a "target lost" message is sent once, then PLND_TIMEOUT (_retry_timeout_s, default 4 s) is how
long the vehicle keeps descending anyway before PLND_STRICT decides whether to retry (climb back up and look again) or just continue a normal landing. This reuses the SITL
backend (PLND_TYPE 4) setup from sitl-copter-precland.py, but once precision landing is actively tracking the target in LAND mode, sets SIM_PLD_ENABLE=0 (the simulated target
simply stops being seen) and watches what actually happens.

    python3 sitl-copter-precland-target-lost.py <ardupilot tree> <out dir> <custom-gcs dir>
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
M_LON = M_LAT * math.cos(math.radians(HOME[0]))
WORK = os.path.expanduser('~/cg-precland-target-lost')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')


def metres(lat1, lon1, lat2, lon2):
    return math.hypot((lat2 - lat1) * M_LAT, (lon2 - lon1) * M_LON)


def position(conn, timeout=5.0):
    msg = conn.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=timeout)
    return (msg.lat / 1e7, msg.lon / 1e7, msg.relative_alt / 1000.0) if msg else None


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    notes, result, proc = [], {}, None
    try:
        proc = subprocess.Popen([BIN, '-w', '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                                stdout=open(os.path.join(WORK, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
        conn, _ = link.connect(5760)
        time.sleep(15)
        base = link.read_params(conn)
        tlat, tlon = HOME[0] + 4 / M_LAT, HOME[1] - 4 / M_LON
        want = {'PLND_ENABLED': 1.0, 'PLND_TYPE': 4.0, 'RNGFND1_TYPE': 1.0, 'RNGFND1_PIN': 0.0, 'RNGFND1_SCALING': 10.0, 'RNGFND1_MIN': 0.0, 'RNGFND1_MAX': 40.0,
                'SIM_SONAR_SCALE': 12.0, 'SIM_PLD_ENABLE': 1.0, 'SIM_PLD_HEIGHT': 0.0, 'SIM_PLD_ALT_LMT': 15.0, 'SIM_PLD_DIST_LMT': 10.0, 'SIM_PLD_LAT': tlat, 'SIM_PLD_LON': tlon}
        changes = [params.Change(n, base.get(n), v) for n, v in want.items()]
        bad = [r.name for r in params.write(conn, changes) if not r.ok]
        notes.append('set %s; rejected %s' % (want, bad))
        notes.append('target %.7f %.7f (4 m north, 4 m west of home)' % (tlat, tlon))
        time.sleep(2)
        proc.terminate()
        proc.wait(10)
        proc = subprocess.Popen([BIN, '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                                stdout=open(os.path.join(WORK, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)
        conn, _ = link.connect(5760, timeout=300.0)
        time.sleep(60)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 33, 200000, 0, 0, 0, 0, 0)
        notes.append('GUIDED: %s' % flight.set_mode(conn, 'GUIDED').detail)
        armed = flight.arm(conn, timeout=150.0)
        notes.append('arm: %s' % armed.detail)
        if armed.ok:
            conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, 10.0)
            begin, p = time.time(), None
            while time.time() - begin < 40.0:
                p = position(conn)
                if p and p[2] >= 9.0:
                    break
            notes.append('climb: %s after %.0f s' % (p, time.time() - begin))
            notes.append('LAND: %s' % flight.set_mode(conn, 'LAND').detail)

            start_t, injected, last = time.time(), False, None
            while time.time() - start_t < 90.0:
                msg = conn.recv_match(type=['HEARTBEAT', 'GLOBAL_POSITION_INT', 'STATUSTEXT'], blocking=True, timeout=1)
                if msg is None:
                    continue
                now = time.time() - start_t
                t = msg.get_type()
                if t == 'GLOBAL_POSITION_INT':
                    last = (msg.lat / 1e7, msg.lon / 1e7, msg.relative_alt / 1000.0)
                    if not injected and last[2] < 6.0:
                        injected = True
                        bad = [r.name for r in params.write(conn, [params.Change('SIM_PLD_ENABLE', 1.0, 0.0)]) if not r.ok]
                        notes.append('t=%5.1f s height %.1f m - fault injected SIM_PLD_ENABLE=0 (target no longer seen) (rejected %s)' % (now, last[2], bad))
                elif t == 'STATUSTEXT':
                    notes.append('t=%5.1f s vehicle: %s' % (now, msg.text))
                elif msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                    if injected and not flight.is_armed(msg):
                        notes.append('t=%5.1f s disarmed, stopping watch' % now)
                        break
            if last:
                result['last_position'] = last
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
    result['notes'] = notes
    with open(os.path.join(OUT, 'precland-target-lost-result.json'), 'w') as f:
        json.dump(result, f, indent=1)
    print('[precland-target-lost] %s' % result, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
