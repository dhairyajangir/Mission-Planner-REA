"""The prototype's parameter, mode, arm, mission and failsafe functions against disposable Rover simulators (WSL, ArduPilot SITL, pymavlink). Simulator only.

    python3 run_rover.py <ardupilot tree> <out dir> [part ...]      parts: basics, mission, failsafes (default: all)

basics    parameters (save, diff, dry run, restore, protected names), every Rover flight mode requested disarmed and armed, arm and disarm.
mission   a mission (home, a waypoint 60 m north, a waypoint 60 m east, RETURN_TO_LAUNCH) driven in AUTO at 3 m/s: items reached, positions, return near home.
failsafes five scenarios, each driving the same mission and injecting a fault 10 s after AUTO starts:
          gcs-link-loss-rtl (FS_GCS_ENABLE 1, FS_ACTION 1) -> RTL; gcs-link-loss-hold (FS_GCS_ENABLE 1, FS_ACTION 2) -> HOLD; battery-low-rtl (BATT_FS_LOW_ACT 1) -> RTL;
          gps-loss-hold (FS_EKF_ACTION 1, GPS disabled) -> HOLD; fence-breach (polygon of +-40 m, FENCE_ENABLE 1) -> a mode other than AUTO (recorded).
Each scenario that a check fails keeps its output as the record.
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
PARTS = sys.argv[3:] or ['basics', 'mission', 'failsafes']
HOME = (-35.363261, 149.165230, 584.0)
TABLE = 'rover'
LEG_DEG_LAT, LEG_DEG_LON = 0.00054, 0.00066            # about 60 m north and 60 m east at this latitude
INJECT_AFTER_S = 10.0
WAYPOINT_TOLERANCE_M = 6.0
FAILSAFES = {
    'gcs-link-loss-rtl': dict(pre={'FS_GCS_ENABLE': 1, 'FS_ACTION': 1}, inject=None, stop_heartbeats=True, expect='RTL'),
    'gcs-link-loss-hold': dict(pre={'FS_GCS_ENABLE': 1, 'FS_ACTION': 2}, inject=None, stop_heartbeats=True, expect='HOLD'),
    'battery-low-rtl': dict(pre={'BATT_FS_LOW_ACT': 1, 'BATT_LOW_VOLT': 11.0, 'BATT_LOW_TIMER': 1}, inject={'SIM_BATT_VOLTAGE': 10.5}, expect='RTL'),
    'gps-loss-hold': dict(pre={'FS_EKF_ACTION': 1}, inject={'SIM_GPS1_ENABLE': 0}, expect='HOLD'),
    'fence-breach': dict(pre={'FENCE_ENABLE': 1, 'FENCE_ACTION': 1}, inject=None, fence=True, expect=None),
}


def metres(lat1, lon1, lat2, lon2):
    return math.hypot((lat2 - lat1) * 111320.0, (lon2 - lon1) * 111320.0 * math.cos(math.radians(lat1)))


def wp(seq, command, x, y, z=0.0, frame=3):
    return mission.Item(seq, frame, command, 1 if seq == 1 else 0, 1, 0.0, 0.0, 0.0, 0.0, x, y, z)


def route():
    north, east = HOME[0] + LEG_DEG_LAT, HOME[1] + LEG_DEG_LON
    return [wp(0, 16, HOME[0], HOME[1], HOME[2], frame=0), wp(1, 16, north, HOME[1]), wp(2, 16, north, HOME[1] + LEG_DEG_LON), wp(3, 20, 0.0, 0.0)], (north, HOME[1]), (north, east)


class Run:
    """One simulator, one record."""

    def __init__(self, name):
        self.name, self.lines, self.failed, self.proc, self.conn, self.beat = name, [], [], None, None, {'on': True}

    def say(self, text=''):
        print('[%s] %s' % (self.name, text), flush=True)
        self.lines.append(text)

    def check(self, label, ok, seen=''):
        self.say('%-4s %s%s' % ('OK' if ok else 'FAIL', label, ('   [' + str(seen) + ']') if seen != '' else ''))
        if not ok:
            self.failed.append(label)
        return ok

    def start(self):
        work = os.path.expanduser('~/cg-rover')
        subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
        time.sleep(1)
        subprocess.call(['rm', '-rf', work])
        os.makedirs(work)
        self.proc = subprocess.Popen([os.path.join(TREE, 'build/sitl/bin/ardurover'), '-w', '--model', 'rover', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME],
                                     cwd=work, stdout=open(os.path.join(work, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
        self.conn, _ = link.connect(5760)
        self.conn.mav.command_long_send(self.conn.target_system, self.conn.target_component, 511, 0, 33, 100000, 0, 0, 0, 0, 0)
        self.conn.mav.heartbeat_send(6, 8, 0, 0, 0)

        def beats():
            while self.beat['on']:
                try:
                    self.conn.mav.heartbeat_send(6, 8, 0, 0, 0)
                except Exception:
                    return
                time.sleep(1.0)
        threading.Thread(target=beats, daemon=True).start()
        time.sleep(40)

    def stop(self):
        self.beat['on'] = False
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except Exception:
                self.proc.kill()

    def finish(self, extra=None):
        self.lines.append('RESULT %s' % ('passed' if not self.failed else '%d checks failed: %s' % (len(self.failed), '; '.join(self.failed))))
        with open(os.path.join(OUT, self.name + '.txt'), 'w') as f:
            f.write('\n'.join(self.lines) + '\n')
        if extra:
            with open(os.path.join(OUT, self.name + '-track.csv'), 'w', newline='') as f:
                w = csv.writer(f)
                w.writerow(['seconds', 'lat', 'lon', 'ground_speed_ms', 'mode'])
                w.writerows(extra)


def set_params(conn, values):
    base = link.read_params(conn)
    return [r for r in params.write(conn, [params.Change(n, base.get(n), float(v)) for n, v in values.items()]) if not r.ok]


def sweep(run, label):
    run.say('-- every mode requested one by one, %s' % label)
    for name, number in sorted(flight.vehicle_modes(TABLE).items(), key=lambda kv: kv[1]):
        result = flight.set_mode(run.conn, name, table=TABLE)
        run.say('mode %2d %-10s %s%s' % (number, name, result.detail, ('  | ' + '; '.join(result.texts[-2:])) if result.texts else ''))
    flight.set_mode(run.conn, 'MANUAL', table=TABLE)


def basics():
    run = Run('rover-basics')
    try:
        run.start()
        conn = run.conn
        run.say('== modes and arming')
        hb = flight.current_heartbeat(conn)
        run.check('vehicle is disarmed and reports a Rover mode', hb is not None and not flight.is_armed(hb), flight.mode_name(hb.custom_mode, TABLE) if hb else None)
        sweep(run, 'disarmed')
        run.check('MANUAL is accepted', flight.set_mode(conn, 'MANUAL', table=TABLE).ok)
        armed = flight.arm(conn, timeout=120.0)
        run.check('arm succeeds', armed.ok, armed.detail + (' | ' + '; '.join(armed.texts[-3:]) if armed.texts else ''))
        hb = flight.current_heartbeat(conn)
        run.check('heartbeat reports armed', hb is not None and flight.is_armed(hb))
        try:
            params.restore(conn, {'WP_SPEED': 2.0}, link.read_params, armed=bool(hb is not None and flight.is_armed(hb)))
            run.check('parameter restore refuses while armed', False)
        except RuntimeError as e:
            run.check('parameter restore refuses while armed', True, e)
        sweep(run, 'armed, standing still in the simulator')
        off = flight.disarm(conn)
        run.check('disarm succeeds', off.ok, off.detail)
        run.say('== parameters')
        base = link.read_params(conn)
        saved = params.loads(params.dumps(base))
        run.check('saved file reloads to the same %d parameters' % len(base), params.diff(base, saved) == [] and params.diff(saved, base) == [])
        changes = [params.Change('WP_SPEED', base['WP_SPEED'], 3.0), params.Change('CRUISE_SPEED', base['CRUISE_SPEED'], 4.0), params.Change('WP_RADIUS', base['WP_RADIUS'], 4.0)]
        results = params.write(conn, changes)
        run.check('three parameters written and echoed', all(r.ok for r in results), [(r.name, r.got) for r in results])
        changed = [c.name for c in params.diff(base, link.read_params(conn)) if not params.protected(c.name)]
        run.check('diff lists exactly those three', sorted(changed) == ['CRUISE_SPEED', 'WP_RADIUS', 'WP_SPEED'], changed)
        tampered = dict(saved)
        tampered['SERIAL0_BAUD'] = saved['SERIAL0_BAUD'] + 1
        report = params.restore(conn, tampered, link.read_params, armed=False)
        after = link.read_params(conn)
        left = [c.name for c in params.diff(after, saved) if not params.protected(c.name)]
        run.check('restore wrote three, skipped the protected SERIAL0_BAUD, vehicle matches the file again', sorted(c.name for c in report.planned) == ['CRUISE_SPEED', 'WP_RADIUS', 'WP_SPEED']
                  and report.skipped_protected == ('SERIAL0_BAUD',) and left == [], (report.skipped_protected, left[:5]))
    except Exception as e:
        run.check('basics finished without an exception', False, repr(e))
    finally:
        run.stop()
        run.finish()


def drive(run, spec):
    """Fly the route in AUTO. spec: pre (parameters), inject, stop_heartbeats, fence, expect (mode name or None). Returns the track."""
    conn = run.conn
    items, p1, p2 = route()
    if spec.get('pre') is not None:
        bad = set_params(conn, dict(spec['pre'], WP_SPEED=3.0, CRUISE_SPEED=3.0))
        run.check('preset parameters %s accepted' % sorted(spec['pre']), not bad, [b.name for b in bad])
    if spec.get('fence'):
        d_lat, d_lon = 0.00036, 0.00044                      # about 40 m each way
        square = mission.fence_polygon([(HOME[0] + d_lat, HOME[1] - d_lon), (HOME[0] + d_lat, HOME[1] + d_lon), (HOME[0] - d_lat, HOME[1] + d_lon), (HOME[0] - d_lat, HOME[1] - d_lon)])
        run.check('fence polygon uploaded', mission.upload(conn, square, mission_type=mission.FENCE) == 0)
    run.check('mission uploaded and read back equal', mission.upload(conn, items) == 0 and mission.verify(items, mission.download(conn)) == [])
    flight.set_mode(conn, 'MANUAL', table=TABLE)
    armed = flight.arm(conn, timeout=120.0)
    run.check('armed', armed.ok, armed.detail + (' | ' + '; '.join(armed.texts[-3:]) if not armed.ok else ''))
    if not armed.ok:
        return []
    auto = flight.set_mode(conn, 'AUTO', table=TABLE)
    retry = time.time() + 60.0
    while not auto.ok and time.time() < retry:
        time.sleep(3)
        auto = flight.set_mode(conn, 'AUTO', table=TABLE)
    run.check('AUTO accepted', auto.ok, auto.detail + (' | ' + '; '.join(auto.texts[-2:]) if not auto.ok else ''))
    if not auto.ok:
        return []
    track, reached, modes = [], [], []
    start, injected, last_hb, pos, settled = time.time(), False, None, None, None
    while time.time() - start < 240.0:
        now = time.time() - start
        if not injected and now >= INJECT_AFTER_S:
            injected = True
            if spec.get('inject'):
                bad = set_params(conn, spec['inject'])
                run.say('t=%5.1f s injected %s%s' % (now, spec['inject'], ' (not accepted: %s)' % [b.name for b in bad] if bad else ''))
            if spec.get('stop_heartbeats'):
                run.beat['on'] = False
                run.say('t=%5.1f s stopped sending ground-station heartbeats' % now)
        msg = conn.recv_match(type=['MISSION_ITEM_REACHED', 'GLOBAL_POSITION_INT', 'HEARTBEAT', 'STATUSTEXT'], blocking=True, timeout=1)
        if msg is None:
            continue
        kind = msg.get_type()
        if kind == 'GLOBAL_POSITION_INT':
            pos = (msg.lat / 1e7, msg.lon / 1e7, math.hypot(msg.vx, msg.vy) / 100.0)
            track.append([round(now, 1), pos[0], pos[1], round(pos[2], 2), flight.mode_name(last_hb.custom_mode, TABLE) if last_hb else ''])
        elif kind == 'MISSION_ITEM_REACHED' and msg.seq != 65535:
            reached.append(msg.seq)
            run.say('t=%5.1f s item %d reached at %s' % (now, msg.seq, ('%.6f, %.6f' % pos[:2]) if pos else '?'))
            if msg.seq in (1, 2) and pos and not spec.get('expect') and not spec.get('fence') and not spec.get('stop_heartbeats'):
                target = p1 if msg.seq == 1 else p2
                run.check('item %d reached within %.0f m' % (msg.seq, WAYPOINT_TOLERANCE_M), metres(pos[0], pos[1], target[0], target[1]) <= WAYPOINT_TOLERANCE_M, '%.1f m off' % metres(pos[0], pos[1], target[0], target[1]))
        elif kind == 'STATUSTEXT':
            run.say('t=%5.1f s vehicle: %s' % (now, msg.text))
        elif kind == 'HEARTBEAT' and msg.get_srcComponent() == 1 and msg.type not in (6, 27):
            if last_hb is None or last_hb.custom_mode != msg.custom_mode or flight.is_armed(last_hb) != flight.is_armed(msg):
                modes.append(flight.mode_name(msg.custom_mode, TABLE))
                run.say('t=%5.1f s heartbeat: %s, mode %s' % (now, 'ARMED' if flight.is_armed(msg) else 'DISARMED', flight.mode_name(msg.custom_mode, TABLE)))
            last_hb = msg
        # stop when the vehicle has come to rest after the route or a failsafe (speed under 0.3 m/s for 15 s), or has disarmed
        if pos and now > INJECT_AFTER_S + 5:
            settled = settled if (pos[2] < 0.3 and settled is not None) else (now if pos[2] < 0.3 else None)
            if settled is not None and now - settled > 15.0:
                break
        if last_hb is not None and not flight.is_armed(last_hb) and now > 20:
            break
    run.say('items reached: %s; modes seen: %s' % (reached, modes))
    if pos:
        run.say('final position %.1f m from home, speed %.2f m/s' % (metres(pos[0], pos[1], HOME[0], HOME[1]), pos[2]))
    after_auto = [m for m in modes if m not in ('AUTO', 'MANUAL')]
    if spec.get('expect'):
        run.check('after the fault the mode changed to %s' % spec['expect'], bool(after_auto) and after_auto[0] == spec['expect'], modes)
    elif spec.get('fence'):
        run.check('the fence breach changed the mode away from AUTO (mode recorded)', bool(after_auto), modes)
    else:
        run.check('items reached in order 1, 2, 3', [r for r in reached if r in (1, 2, 3)] == [1, 2, 3], reached)
        run.check('the vehicle came back to within 6 m of home', pos is not None and metres(pos[0], pos[1], HOME[0], HOME[1]) <= 6.0, '%.1f m' % metres(pos[0], pos[1], HOME[0], HOME[1]) if pos else '')
    off = flight.disarm(conn)
    run.say('disarm at the end: %s' % off.detail)
    return track


def scenario(name, spec):
    run = Run(name)
    track = []
    try:
        run.start()
        track = drive(run, spec)
    except Exception as e:
        run.check('%s finished without an exception' % name, False, repr(e))
    finally:
        run.stop()
        run.finish(track)
    return not run.failed


def main():
    os.makedirs(OUT, exist_ok=True)
    results = []
    if 'basics' in PARTS:
        basics()
    if 'mission' in PARTS:
        results.append(('rover-mission', scenario('rover-mission', dict(pre={}, expect=None))))
    if 'failsafes' in PARTS:
        for name, spec in FAILSAFES.items():
            results.append((name, scenario('rover-' + name, spec)))
    for name, ok in results:
        print('SCENARIO %s %s' % (name, 'passed' if ok else 'FAILED'), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
