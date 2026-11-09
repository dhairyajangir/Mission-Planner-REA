"""The prototype's parameter, mode, arm and mission functions against a disposable fixed-wing ArduPlane simulator (WSL, ArduPilot SITL, pymavlink). Simulator only.

    python3 run_plane.py <ardupilot tree> <out dir> [part ...]       parts: basics, mission (default: both)

basics   parameters (save, diff, dry run, restore, protected names), every Plane flight mode requested while DISARMED (an armed plane would take off in TAKEOFF or AUTO, so the
         armed sweep is limited to MANUAL and FLY_BY_WIRE_A), arm and disarm.
mission  a mission flown in AUTO: TAKEOFF to 60 m, a waypoint 300 m north, one 300 m east of that, one 300 m south of that, and a LAND at the home position, approached from the east.
         Checks: items reached in order, positions at the waypoints within 60 m (the vehicle's own WP_RADIUS is 50 m), altitude near the commanded 60 m, the landing completes
         and the vehicle disarms itself. A flight track (CSV) is kept.
failsafes the same flight with a fault injected 15 s after AUTO starts (after takeoff): gcs-link-loss (FS_GCS_ENABL 1, FS_LONG_ACTN 1) -> RTL; rc-loss (SIM_RC_FAIL 1,
         FS_LONG_ACTN 1) -> RTL; battery-low (BATT_FS_LOW_ACT 1) -> RTL; circle-fence (FENCE_TYPE 2, radius 200 m, action 1) -> RTL; wind-10ms (no failsafe: the mission must finish);
         gps-loss (GPS disabled in the simulator: reaction recorded; the check is that the aircraft is still flying above 20 m, or has landed and disarmed, 60 s later).
inflight after an AUTO takeoff (item 1 reached) the script requests FLY_BY_WIRE_A, FLY_BY_WIRE_B, CRUISE, STABILIZE, LOITER, CIRCLE, GUIDED and RTL in turn and holds each for 10 s,
         recording whether it became active and the altitude and ground speed at the start and end of the hold. With no radio input in the simulator, the modes that need the pilot's
         throttle (FLY_BY_WIRE_A, STABILIZE) are expected to lose height; that is recorded, not judged. A mode passes when the vehicle reports it within 5 s and is still airborne
         (above 15 m) 10 s later.
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
PARTS = sys.argv[3:] or ['basics', 'mission', 'failsafes', 'inflight']
HOME = (-35.363261, 149.165230, 584.0)
TABLE = 'plane'
INJECT_AFTER_S = 15.0
FAILSAFES = {
    'gcs-link-loss': dict(pre={'FS_GCS_ENABL': 1, 'FS_LONG_ACTN': 1, 'FS_LONG_TIMEOUT': 5}, inject=None, stop_heartbeats=True, expect='RTL'),
    'rc-loss': dict(pre={'FS_LONG_ACTN': 1, 'FS_LONG_TIMEOUT': 5}, inject={'SIM_RC_FAIL': 1}, expect='RTL'),
    'battery-low': dict(pre={'BATT_FS_LOW_ACT': 1, 'BATT_LOW_VOLT': 11.0, 'BATT_LOW_TIMER': 1}, inject={'SIM_BATT_VOLTAGE': 10.5}, expect='RTL'),
    'circle-fence': dict(pre={'FENCE_ENABLE': 1, 'FENCE_TYPE': 2, 'FENCE_RADIUS': 200, 'FENCE_ACTION': 1}, inject=None, expect='RTL'),
    'wind-10ms': dict(pre={}, inject={'SIM_WIND_SPD': 10.0, 'SIM_WIND_DIR': 90.0}, expect='complete'),
    'gps-loss': dict(pre={}, inject={'SIM_GPS1_ENABLE': 0}, expect='observe'),          # no configured action exists for this: the reaction is recorded, the check is that the aircraft does not crash within 60 s
}
M_PER_DEG_LAT = 111320.0
LEG_DEG = 300.0 / M_PER_DEG_LAT
LEG_DEG_LON = 300.0 / (M_PER_DEG_LAT * math.cos(math.radians(35.363261)))
WAYPOINT_TOLERANCE_M = 60.0
CRUISE_ALT_M = 60.0


def metres(lat1, lon1, lat2, lon2):
    return math.hypot((lat2 - lat1) * M_PER_DEG_LAT, (lon2 - lon1) * M_PER_DEG_LAT * math.cos(math.radians(lat1)))


def wp(seq, command, x, y, z, frame=3, p1=0.0):
    return mission.Item(seq, frame, command, 1 if seq == 1 else 0, 1, p1, 0.0, 0.0, 0.0, x, y, z)


def route():
    a = (HOME[0] + LEG_DEG, HOME[1])
    b = (a[0], a[1] + LEG_DEG_LON)
    c = (HOME[0], b[1])
    items = [wp(0, 16, HOME[0], HOME[1], HOME[2], frame=0), wp(1, 22, 0.0, 0.0, CRUISE_ALT_M, p1=15.0), wp(2, 16, a[0], a[1], CRUISE_ALT_M), wp(3, 16, b[0], b[1], CRUISE_ALT_M),
             wp(4, 16, c[0], c[1], 40.0), wp(5, 21, HOME[0], HOME[1], 0.0)]
    return items, {2: a, 3: b, 4: c}


class Run:
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
        work = os.path.expanduser('~/cg-plane')
        subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
        time.sleep(1)
        subprocess.call(['rm', '-rf', work])
        os.makedirs(work)
        self.proc = subprocess.Popen([os.path.join(TREE, 'build/sitl/bin/arduplane'), '-w', '--model', 'plane', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME],
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

    def finish(self, track=None):
        self.lines.append('RESULT %s' % ('passed' if not self.failed else '%d checks failed: %s' % (len(self.failed), '; '.join(self.failed))))
        with open(os.path.join(OUT, self.name + '.txt'), 'w') as f:
            f.write('\n'.join(self.lines) + '\n')
        if track:
            with open(os.path.join(OUT, self.name + '-track.csv'), 'w', newline='') as f:
                w = csv.writer(f)
                w.writerow(['seconds', 'lat', 'lon', 'relative_alt_m', 'ground_speed_ms', 'mode'])
                w.writerows(track)


def basics():
    run = Run('plane-basics')
    try:
        run.start()
        conn = run.conn
        run.say('== modes and arming')
        hb = flight.current_heartbeat(conn)
        run.check('vehicle is disarmed and reports a Plane mode', hb is not None and not flight.is_armed(hb), flight.mode_name(hb.custom_mode, TABLE) if hb else None)
        run.say('-- every mode requested one by one, disarmed')
        for name, number in sorted(flight.vehicle_modes(TABLE).items(), key=lambda kv: kv[1]):
            result = flight.set_mode(conn, name, table=TABLE)
            run.say('mode %2d %-17s %s%s' % (number, name, result.detail, ('  | ' + '; '.join(result.texts[-2:])) if result.texts else ''))
        run.check('MANUAL is accepted', flight.set_mode(conn, 'MANUAL', table=TABLE).ok)
        armed = flight.arm(conn, timeout=120.0)
        run.check('arm succeeds', armed.ok, armed.detail + (' | ' + '; '.join(armed.texts[-3:]) if armed.texts else ''))
        hb = flight.current_heartbeat(conn)
        run.check('heartbeat reports armed', hb is not None and flight.is_armed(hb))
        try:
            params.restore(conn, {'WP_RADIUS': 40.0}, link.read_params, armed=bool(hb is not None and flight.is_armed(hb)))
            run.check('parameter restore refuses while armed', False)
        except RuntimeError as e:
            run.check('parameter restore refuses while armed', True, e)
        for name in ('FLY_BY_WIRE_A', 'MANUAL'):
            result = flight.set_mode(conn, name, table=TABLE)
            run.check('%s accepted while armed on the ground' % name, result.ok, result.detail)
        off = flight.disarm(conn)
        run.check('disarm succeeds', off.ok, off.detail)
        run.say('== parameters')
        base = link.read_params(conn)
        saved = params.loads(params.dumps(base))
        run.check('saved file reloads to the same %d parameters' % len(base), params.diff(base, saved) == [] and params.diff(saved, base) == [])
        changes = [params.Change('AIRSPEED_CRUISE', base['AIRSPEED_CRUISE'], 20.0), params.Change('WP_RADIUS', base['WP_RADIUS'], 60.0), params.Change('RTL_ALTITUDE', base['RTL_ALTITUDE'], 80.0)]
        results = params.write(conn, changes)
        run.check('three parameters written and echoed', all(r.ok for r in results), [(r.name, r.got) for r in results])
        changed = [c.name for c in params.diff(base, link.read_params(conn)) if not params.protected(c.name)]
        run.check('diff lists exactly those three', sorted(changed) == ['AIRSPEED_CRUISE', 'RTL_ALTITUDE', 'WP_RADIUS'], changed)
        tampered = dict(saved)
        tampered['SERIAL0_BAUD'] = saved['SERIAL0_BAUD'] + 1
        report = params.restore(conn, tampered, link.read_params, armed=False)
        after = link.read_params(conn)
        left = [c.name for c in params.diff(after, saved) if not params.protected(c.name)]
        run.check('restore wrote three, left the protected names alone, vehicle matches the file again', sorted(c.name for c in report.planned) == ['AIRSPEED_CRUISE', 'RTL_ALTITUDE', 'WP_RADIUS']
                  and 'SERIAL0_BAUD' in report.skipped_protected and left == [], (report.skipped_protected, left[:5]))
    except Exception as e:
        run.check('basics finished without an exception', False, repr(e))
    finally:
        run.stop()
        run.finish()


def fly(name='plane-mission', spec=None):
    spec = spec or {}
    run = Run(name)
    track = []
    try:
        run.start()
        conn = run.conn
        if spec.get('pre'):
            base = link.read_params(conn)
            bad = [r.name for r in params.write(conn, [params.Change(n, base.get(n), float(v)) for n, v in spec['pre'].items()]) if not r.ok]
            run.check('preset parameters %s accepted' % sorted(spec['pre']), not bad, bad)
        items, targets = route()
        run.say('route: takeoff to %.0f m, A %.0f m north, B 300 m east of A, C 300 m south of B (40 m), LAND at home' % (CRUISE_ALT_M, 300))
        run.check('mission uploaded', mission.upload(conn, items) == 0)
        got = mission.download(conn)
        problems = mission.verify(items, got, ignore=((21, 'param4'),))       # the Plane returns param4 1.0 for a NAV_LAND item sent with 0.0 (first run, plane-mission-run1-*)
        run.check('mission reads back equal (NAV_LAND param4 aside)', problems == [], problems[:3])
        flight.set_mode(conn, 'MANUAL', table=TABLE)
        armed = flight.arm(conn, timeout=120.0)
        run.check('armed', armed.ok, armed.detail + (' | ' + '; '.join(armed.texts[-3:]) if not armed.ok else ''))
        if not armed.ok:
            return
        auto = flight.set_mode(conn, 'AUTO', table=TABLE)
        retry = time.time() + 60.0
        while not auto.ok and time.time() < retry:
            time.sleep(3)
            auto = flight.set_mode(conn, 'AUTO', table=TABLE)
        run.check('AUTO accepted', auto.ok, auto.detail + (' | ' + '; '.join(auto.texts[-2:]) if not auto.ok else ''))
        if not auto.ok:
            return
        reached, pos, last_hb, start, announced_land = [], None, None, time.time(), False
        injected, modes, expect_seen_at = False, [], None
        while time.time() - start < 420.0:
            now = time.time() - start
            if not injected and now >= INJECT_AFTER_S and (spec.get('inject') or spec.get('stop_heartbeats')):
                injected = True
                if spec.get('inject'):
                    base = link.read_params(conn)
                    bad = [r.name for r in params.write(conn, [params.Change(n, base.get(n), float(v)) for n, v in spec['inject'].items()]) if not r.ok]
                    run.say('t=%5.1f s injected %s%s' % (now, spec['inject'], ' (not accepted: %s)' % bad if bad else ''))
                if spec.get('stop_heartbeats'):
                    run.beat['on'] = False
                    run.say('t=%5.1f s stopped sending ground-station heartbeats' % now)
            if expect_seen_at is not None and now - expect_seen_at > 25.0:
                break                                          # the Plane loiters at the RTL point; nothing more to learn
            if spec.get('expect') == 'observe' and injected and now > INJECT_AFTER_S + 60.0:
                break
            msg = conn.recv_match(type=['MISSION_ITEM_REACHED', 'GLOBAL_POSITION_INT', 'HEARTBEAT', 'STATUSTEXT'], blocking=True, timeout=1)
            if msg is None:
                continue
            kind = msg.get_type()
            if kind == 'GLOBAL_POSITION_INT':
                pos = (msg.lat / 1e7, msg.lon / 1e7, msg.relative_alt / 1000.0, math.hypot(msg.vx, msg.vy) / 100.0)
                track.append([round(now, 1), pos[0], pos[1], round(pos[2], 1), round(pos[3], 1), flight.mode_name(last_hb.custom_mode, TABLE) if last_hb else ''])
            elif kind == 'MISSION_ITEM_REACHED' and msg.seq != 65535:
                reached.append(msg.seq)
                run.say('t=%5.1f s item %d reached at %s' % (now, msg.seq, ('%.6f, %.6f, %.0f m' % pos[:3]) if pos else '?'))
                if msg.seq in targets and pos:
                    off = metres(pos[0], pos[1], targets[msg.seq][0], targets[msg.seq][1])
                    want = CRUISE_ALT_M if msg.seq != 4 else 40.0
                    run.check('item %d reached within %.0f m horizontally and 15 m of the commanded %.0f m' % (msg.seq, WAYPOINT_TOLERANCE_M, want), off <= WAYPOINT_TOLERANCE_M and abs(pos[2] - want) <= 15.0,
                              '%.0f m off, %.0f m up' % (off, pos[2]))
            elif kind == 'STATUSTEXT':
                run.say('t=%5.1f s vehicle: %s' % (now, msg.text))
                announced_land = announced_land or msg.text.startswith('Mission: 5 Land')
            elif kind == 'HEARTBEAT' and msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                if last_hb is None or last_hb.custom_mode != msg.custom_mode or flight.is_armed(last_hb) != flight.is_armed(msg):
                    modes.append(flight.mode_name(msg.custom_mode, TABLE))
                    run.say('t=%5.1f s heartbeat: %s, mode %s' % (now, 'ARMED' if flight.is_armed(msg) else 'DISARMED', flight.mode_name(msg.custom_mode, TABLE)))
                last_hb = msg
                if not flight.is_armed(msg) and now > 30:
                    break
                if spec.get('expect') == 'RTL' and flight.mode_name(msg.custom_mode, TABLE) == 'RTL' and expect_seen_at is None:
                    expect_seen_at = now
        peak = max((t[3] for t in track), default=0.0)
        wanted = spec.get('expect')
        if wanted in (None, 'complete'):
            run.check('items 1 to 4 reached in order and the vehicle began item 5 (the landing; a Plane does not report that item as reached)', [r for r in reached if 1 <= r <= 5] == [1, 2, 3, 4] and announced_land, reached)
            run.check('peak altitude 45 m or more', peak >= 45.0, 'peak %.0f m' % peak)
            run.check('the vehicle disarmed by itself after landing', last_hb is not None and not flight.is_armed(last_hb))
            if pos:
                run.check('came to rest within 150 m of the home position', metres(pos[0], pos[1], HOME[0], HOME[1]) <= 150.0, '%.0f m from home, %.0f m up' % (metres(pos[0], pos[1], HOME[0], HOME[1]), pos[2]))
            if wanted == 'complete':
                run.check('no failsafe mode change: the vehicle stayed in AUTO', set(modes) <= {'AUTO', 'MANUAL'}, modes)
        elif wanted == 'observe':
            flying = pos is not None and (pos[2] > 20.0 or (last_hb is not None and not flight.is_armed(last_hb)))
            run.say('modes seen: %s; items reached: %s' % (modes, reached))
            run.check('60 s after the fault the aircraft is flying above 20 m or has landed and disarmed (no crash)', flying, ('%.0f m up' % pos[2]) if pos else '')
        else:
            after_auto = [m for m in modes if m not in ('AUTO', 'MANUAL')]
            run.check('after the fault the mode changed to %s' % wanted, bool(after_auto) and after_auto[0] == wanted, modes)
            if pos:
                run.say('position at the end: %.0f m from home, %.0f m up' % (metres(pos[0], pos[1], HOME[0], HOME[1]), pos[2]))
    except Exception as e:
        run.check('mission finished without an exception', False, repr(e))
    finally:
        run.stop()
        run.finish(track)


def inflight():
    run = Run('plane-modes-in-flight')
    track = []
    try:
        run.start()
        conn = run.conn
        items, _ = route()
        run.check('mission uploaded', mission.upload(conn, items) == 0)
        flight.set_mode(conn, 'MANUAL', table=TABLE)
        armed = flight.arm(conn, timeout=120.0)
        run.check('armed', armed.ok, armed.detail)
        auto = flight.set_mode(conn, 'AUTO', table=TABLE)
        retry = time.time() + 60.0
        while not auto.ok and time.time() < retry:
            time.sleep(3)
            auto = flight.set_mode(conn, 'AUTO', table=TABLE)
        run.check('AUTO accepted', auto.ok, auto.detail)
        if not (armed.ok and auto.ok):
            return
        state = {'pos': None}

        def watch(seconds):
            end = time.time() + seconds
            while time.time() < end:
                msg = conn.recv_match(type=['GLOBAL_POSITION_INT', 'STATUSTEXT'], blocking=True, timeout=0.5)
                if msg is None:
                    continue
                if msg.get_type() == 'GLOBAL_POSITION_INT':
                    state['pos'] = (msg.lat / 1e7, msg.lon / 1e7, msg.relative_alt / 1000.0, math.hypot(msg.vx, msg.vy) / 100.0)
                    track.append([round(time.time() - t0, 1), state['pos'][0], state['pos'][1], round(state['pos'][2], 1), round(state['pos'][3], 1), current[0]])
                else:
                    run.say('        vehicle: %s' % msg.text)
        t0 = time.time()
        current = ['AUTO']
        deadline = time.time() + 90.0
        watch(1.0)
        while time.time() < deadline:                                   # wait for the takeoff to finish (item 1 reached shows as 55 m or more)
            watch(1.0)
            if state['pos'] and state['pos'][2] >= 55.0:
                break
        run.check('airborne above 50 m after the AUTO takeoff', bool(state['pos']) and state['pos'][2] >= 50.0, ('%.0f m' % state['pos'][2]) if state['pos'] else '')
        for name in ('FLY_BY_WIRE_A', 'FLY_BY_WIRE_B', 'CRUISE', 'STABILIZE', 'LOITER', 'CIRCLE', 'GUIDED', 'RTL'):
            before = state['pos']
            result = flight.set_mode(conn, name, timeout=5.0, table=TABLE)
            current[0] = name if result.ok else current[0]
            watch(10.0)
            after = state['pos']
            run.say('%-14s %s | start %s | after 10 s %s' % (name, result.detail, ('%.0f m, %.1f m/s' % (before[2], before[3])) if before else '?', ('%.0f m, %.1f m/s' % (after[2], after[3])) if after else '?'))
            run.check('%s became active and the aircraft was still above 15 m 10 s later' % name, result.ok and after is not None and after[2] > 15.0, (result.detail, ('%.0f m' % after[2]) if after else ''))
            if after is not None and after[2] <= 15.0:
                break
    except Exception as e:
        run.check('inflight finished without an exception', False, repr(e))
    finally:
        run.stop()
        run.finish(track)


def main():
    os.makedirs(OUT, exist_ok=True)
    if 'basics' in PARTS:
        basics()
    if 'mission' in PARTS:
        fly()
    chosen = [x.split(':', 1)[1] for x in PARTS if x.startswith('failsafe:')]          # failsafe:gps-loss runs one scenario
    if 'failsafes' in PARTS or chosen:
        for name, spec in FAILSAFES.items():
            if 'failsafes' in PARTS or name in chosen:
                fly('plane-' + name, spec)
    if 'inflight' in PARTS:
        inflight()
    return 0


if __name__ == '__main__':
    sys.exit(main())
