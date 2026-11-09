"""Failsafes and a second fence action, observed through the prototype on disposable Copter simulators (WSL, ArduPilot SITL, pymavlink). Simulator only.

Each scenario starts a fresh simulator, sets some parameters, uploads the same three-leg mission as run_flight.py, arms, flies it in AUTO and, 12 s after the mission start,
injects a fault. The vehicle's reaction (flight mode changes, STATUSTEXT, where it ends up) is recorded; a scenario passes when the mode changes to the one the configured
action asks for and the vehicle disarms by itself. Scenarios:

  battery-low-rtl       BATT_FS_LOW_ACT 2 (RTL), BATT_LOW_VOLT 11, then SIM_BATT_VOLTAGE 10.5     -> expects RTL
  battery-critical-land BATT_FS_CRT_ACT 1 (Land), BATT_CRT_VOLT 10, then SIM_BATT_VOLTAGE 9       -> expects LAND
  gps-loss              FS_EKF_ACTION 1 (Land), then SIM_GPS1_ENABLE 0                            -> expects LAND (or an EKF reaction; recorded)
  gcs-link-loss         FS_GCS_ENABLE 1 (RTL), FS_GCS_TIMEOUT 5, then this script stops its heartbeats -> expects RTL
  fence-always-land     polygon fence of +-60 m, FENCE_ENABLE 1, FENCE_ACTION 2 (always land)      -> expects LAND at the breach (no injection)

    python3 run_failsafes.py <ardupilot tree> <out dir> [scenario ...]
"""
import csv
import math
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from customgcs import flight, link, mission, params  # noqa: E402

TREE, OUT = sys.argv[1], sys.argv[2]
HOME = (-35.363261, 149.165230, 584.0)
INJECT_AFTER_S = 12.0
SCENARIOS = {
    'battery-low-rtl': dict(pre={'BATT_FS_LOW_ACT': 2, 'BATT_LOW_VOLT': 11.0, 'BATT_LOW_TIMER': 1}, inject={'SIM_BATT_VOLTAGE': 10.5}, expect='RTL'),
    'battery-critical-land': dict(pre={'BATT_FS_CRT_ACT': 1, 'BATT_CRT_VOLT': 10.0, 'BATT_LOW_TIMER': 1}, inject={'SIM_BATT_VOLTAGE': 9.0}, expect='LAND'),
    'gps-loss': dict(pre={'FS_EKF_ACTION': 1}, inject={'SIM_GPS1_ENABLE': 0}, expect='LAND'),
    'gcs-link-loss': dict(pre={'FS_GCS_ENABLE': 1, 'FS_GCS_TIMEOUT': 5}, inject=None, stop_heartbeats=True, expect='RTL'),
    'fence-always-land': dict(pre={'FENCE_ENABLE': 1, 'FENCE_ACTION': 2}, inject=None, fence=True, expect='LAND'),
}


def metres(lat1, lon1, lat2, lon2):
    return math.hypot((lat2 - lat1) * 111320.0, (lon2 - lon1) * 111320.0 * math.cos(math.radians(lat1)))


def wp(seq, command, x, y, z, frame=3):
    return mission.Item(seq, frame, command, 1 if seq == 1 else 0, 1, 0.0, 0.0, 0.0, 0.0, x, y, z)


def set_params(conn, values):
    base = link.read_params(conn)
    results = params.write(conn, [params.Change(n, base.get(n), float(v)) for n, v in values.items()])
    return [r for r in results if not r.ok]


def run(name, spec):
    lines, failed = [], []

    def say(text=''):
        print('[%s] %s' % (name, text), flush=True)
        lines.append(text)

    def check(label, ok, seen=''):
        say('%-4s %s%s' % ('OK' if ok else 'FAIL', label, ('   [' + str(seen) + ']') if seen != '' else ''))
        if not ok:
            failed.append(label)

    work = os.path.expanduser('~/cg-failsafe')
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', work])
    os.makedirs(work)
    proc = subprocess.Popen([os.path.join(TREE, 'build/sitl/bin/arducopter'), '-w', '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME],
                            cwd=work, stdout=open(os.path.join(work, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    track = []
    beat = {'on': True}
    try:
        conn, _ = link.connect(5760)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 33, 100000, 0, 0, 0, 0, 0)
        conn.mav.heartbeat_send(6, 8, 0, 0, 0)                               # a ground-station heartbeat: the GCS failsafe only arms after one has been seen

        def beats():                                                         # a real ground station keeps sending them; they stop only when the scenario says so
            while beat['on']:
                try:
                    conn.mav.heartbeat_send(6, 8, 0, 0, 0)
                except Exception:
                    return
                time.sleep(1.0)
        threading.Thread(target=beats, daemon=True).start()
        time.sleep(50)
        bad = set_params(conn, spec['pre'])
        check('preset parameters %s accepted' % sorted(spec['pre']), not bad, [b.name for b in bad])
        if spec.get('fence'):
            half_lat, half_lon = 0.00054, 0.00066
            square = mission.fence_polygon([(HOME[0] + half_lat, HOME[1] - half_lon), (HOME[0] + half_lat, HOME[1] + half_lon), (HOME[0] - half_lat, HOME[1] + half_lon), (HOME[0] - half_lat, HOME[1] - half_lon)])
            check('fence polygon uploaded', mission.upload(conn, square, mission_type=mission.FENCE) == 0)
        north, east = HOME[0] + 0.0007, HOME[1] + 0.0009
        items = [wp(0, 16, HOME[0], HOME[1], HOME[2], frame=0), wp(1, 22, 0.0, 0.0, 15.0), wp(2, 16, north, HOME[1], 15.0), wp(3, 16, north, east, 15.0), wp(4, 20, 0.0, 0.0, 0.0)]
        check('mission uploaded', mission.upload(conn, items) == 0)
        flight.set_mode(conn, 'STABILIZE')
        armed = flight.arm(conn, timeout=150.0)
        check('armed', armed.ok, armed.detail + (' | ' + '; '.join(armed.texts[-3:]) if not armed.ok else ''))
        if not armed.ok:
            return lines, failed, track
        auto = flight.set_mode(conn, 'AUTO')
        retry = time.time() + 90.0
        while not auto.ok and time.time() < retry:
            time.sleep(3)
            auto = flight.set_mode(conn, 'AUTO')
        check('AUTO accepted', auto.ok, auto.detail)
        if not auto.ok:
            return lines, failed, track
        say('mission start: %s' % flight.start_mission(conn).detail)
        start, injected, last_hb, pos, modes, reached = time.time(), False, None, None, [], []
        while time.time() - start < 300.0:
            now = time.time() - start
            if not injected and now >= INJECT_AFTER_S:
                injected = True
                if spec.get('inject'):
                    bad = set_params(conn, spec['inject'])
                    say('t=%5.1f s injected %s%s' % (now, spec['inject'], ' (not accepted: %s)' % [b.name for b in bad] if bad else ''))
                if spec.get('stop_heartbeats'):
                    beat['on'] = False
                    say('t=%5.1f s stopped sending ground-station heartbeats' % now)
            msg = conn.recv_match(type=['MISSION_ITEM_REACHED', 'GLOBAL_POSITION_INT', 'HEARTBEAT', 'STATUSTEXT'], blocking=True, timeout=1)
            if msg is None:
                continue
            kind = msg.get_type()
            if kind == 'GLOBAL_POSITION_INT':
                pos = (msg.lat / 1e7, msg.lon / 1e7, msg.relative_alt / 1000.0)
                track.append([round(now, 1), pos[0], pos[1], round(pos[2], 2), flight.mode_name(last_hb.custom_mode) if last_hb else ''])
            elif kind == 'MISSION_ITEM_REACHED' and msg.seq != 65535:
                reached.append(msg.seq)
                say('t=%5.1f s item %d reached' % (now, msg.seq))
            elif kind == 'STATUSTEXT':
                say('t=%5.1f s vehicle: %s' % (now, msg.text))
            elif kind == 'HEARTBEAT' and msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                if last_hb is None or last_hb.custom_mode != msg.custom_mode or flight.is_armed(last_hb) != flight.is_armed(msg):
                    modes.append(flight.mode_name(msg.custom_mode))
                    say('t=%5.1f s heartbeat: %s, mode %s' % (now, 'ARMED' if flight.is_armed(msg) else 'DISARMED', flight.mode_name(msg.custom_mode)))
                last_hb = msg
                if not flight.is_armed(msg) and now > 20:
                    break
        after_auto = [m for m in modes if m not in ('AUTO', 'STABILIZE')]
        check('after the fault the mode changed to %s' % spec['expect'], bool(after_auto) and after_auto[0] == spec['expect'], modes)
        check('the vehicle disarmed by itself', last_hb is not None and not flight.is_armed(last_hb))
        if pos:
            say('final position %.1f m from home, %.1f m up' % (metres(pos[0], pos[1], HOME[0], HOME[1]), pos[2]))
        say('items reached: %s' % reached)
    except Exception as e:                                   # keep the failure as the record
        check('scenario finished without an exception', False, repr(e))
    finally:
        beat['on'] = False
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
    return lines, failed, track


def main():
    os.makedirs(OUT, exist_ok=True)
    chosen = sys.argv[3:] or list(SCENARIOS)
    summary = []
    for name in chosen:
        lines, failed, track = run(name, SCENARIOS[name])
        lines.append('RESULT %s' % ('passed' if not failed else '%d checks failed: %s' % (len(failed), '; '.join(failed))))
        with open(os.path.join(OUT, name + '.txt'), 'w') as f:
            f.write('\n'.join(lines) + '\n')
        with open(os.path.join(OUT, name + '-track.csv'), 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['seconds', 'lat', 'lon', 'relative_alt_m', 'mode'])
            w.writerows(track)
        summary.append((name, not failed))
        print('SCENARIO %s %s' % (name, 'passed' if not failed else 'FAILED'), flush=True)
    return 0 if all(ok for _, ok in summary) else 1


if __name__ == '__main__':
    sys.exit(main())
