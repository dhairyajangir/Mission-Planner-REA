"""More mission shapes flown on disposable Copter simulators (WSL, ArduPilot SITL, pymavlink). Simulator only.

    python3 run_copter_missions.py <ardupilot tree> <out dir> [shape ...]

Each shape starts a fresh simulator, uploads the mission through the prototype, arms in STABILIZE, switches to AUTO, sends MISSION_START and follows MISSION_ITEM_REACHED,
GLOBAL_POSITION_INT and the heartbeat until the vehicle disarms. Shapes:

  loiter-speed   TAKEOFF 20 m, DO_CHANGE_SPEED 2 m/s, waypoint 60 m north, LOITER_TIME 10 s 60 m north-east, DO_CHANGE_SPEED 8 m/s, waypoint 60 m east of home, LAND 30 m east of home.
                 Checks: nav items reached in order, the loiter lasted about 10 s, the LAND ended within 5 m of its coordinates (not at home), the leg at 2 m/s was slower than the leg at 8 m/s.
  jump-loop      TAKEOFF 15 m, waypoint north, waypoint north-east, DO_JUMP back to item 2 twice, RETURN_TO_LAUNCH. Check: the reached sequence is the loop run three times, then the RTL.
  spline         TAKEOFF 15 m, three NAV_SPLINE_WAYPOINT items, RETURN_TO_LAUNCH. Checks: items reached in order, each spline point within 6 m, back at home.
"""
import csv
import math
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from customgcs import flight, link, mission  # noqa: E402

TREE, OUT = sys.argv[1], sys.argv[2]
HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(35.363261))
TAKEOFF, WAYPOINT, LOITER_TIME, RTL, LAND, SPLINE, DO_JUMP, DO_CHANGE_SPEED = 22, 16, 19, 20, 21, 82, 177, 178


def at(north_m, east_m):
    return HOME[0] + north_m / M_LAT, HOME[1] + east_m / M_LON


def metres(a, b):
    return math.hypot((b[0] - a[0]) * M_LAT, (b[1] - a[1]) * M_LON)


def item(seq, command, point=(0.0, 0.0), alt=0.0, p1=0.0, p2=0.0, frame=3):
    return mission.Item(seq, frame, command, 1 if seq == 1 else 0, 1, p1, p2, 0.0, 0.0, point[0], point[1], alt)


def shapes():
    home = mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2])
    ne, n, e = at(60, 60), at(60, 0), at(0, 60)
    land_point = at(0, 30)
    loiter_speed = [home, item(1, TAKEOFF, alt=20), item(2, DO_CHANGE_SPEED, p1=1, p2=2.0), item(3, WAYPOINT, n, 20), item(4, LOITER_TIME, ne, 20, p1=10.0),
                    item(5, DO_CHANGE_SPEED, p1=1, p2=8.0), item(6, WAYPOINT, e, 15), item(7, LAND, land_point, 0)]
    jump = [home, item(1, TAKEOFF, alt=15), item(2, WAYPOINT, at(50, 0), 15), item(3, WAYPOINT, at(50, 50), 15), item(4, DO_JUMP, p1=2, p2=2), item(5, RTL)]
    spline = [home, item(1, TAKEOFF, alt=15), item(2, SPLINE, at(40, 0), 15), item(3, SPLINE, at(60, 40), 15), item(4, SPLINE, at(30, 70), 15), item(5, RTL)]
    return {'loiter-speed': (loiter_speed, {2: None}), 'jump-loop': (jump, {}), 'spline': (spline, {2: at(40, 0), 3: at(60, 40), 4: at(30, 70)})}


def run(name, items, spline_targets):
    lines, failed, track = [], [], []

    def say(text=''):
        print('[%s] %s' % (name, text), flush=True)
        lines.append(text)

    def check(label, ok, seen=''):
        say('%-4s %s%s' % ('OK' if ok else 'FAIL', label, ('   [' + str(seen) + ']') if seen != '' else ''))
        if not ok:
            failed.append(label)

    work = os.path.expanduser('~/cg-missions')
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', work])
    os.makedirs(work)
    proc = subprocess.Popen([os.path.join(TREE, 'build/sitl/bin/arducopter'), '-w', '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME],
                            cwd=work, stdout=open(os.path.join(work, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    try:
        conn, _ = link.connect(5760)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 33, 100000, 0, 0, 0, 0, 0)
        time.sleep(50)
        check('mission of %d items uploaded (ack 0)' % len(items), mission.upload(conn, items) == 0)
        back = mission.download(conn)
        problems = mission.verify(items, back, ignore=mission.VEHICLE_REWRITES)         # LOITER_TIME param3 and LAND param4 come back as 1.0 (first run: loiter-speed-run1-*)
        check('mission reads back equal (home aside)', problems == [], problems[:3])
        flight.set_mode(conn, 'STABILIZE')
        armed = flight.arm(conn, timeout=150.0)
        check('armed', armed.ok, armed.detail)
        auto = flight.set_mode(conn, 'AUTO')
        retry = time.time() + 90.0
        while not auto.ok and time.time() < retry:
            time.sleep(3)
            auto = flight.set_mode(conn, 'AUTO')
        check('AUTO accepted', auto.ok, auto.detail)
        if not (armed.ok and auto.ok):
            return lines, failed, track
        say('mission start: %s' % flight.start_mission(conn).detail)
        reached, stamps, said, said_at, pos, last_hb, start = [], [], [], [], None, None, time.time()
        while time.time() - start < 420.0:
            now = time.time() - start
            msg = conn.recv_match(type=['MISSION_ITEM_REACHED', 'GLOBAL_POSITION_INT', 'HEARTBEAT', 'STATUSTEXT'], blocking=True, timeout=1)
            if msg is None:
                continue
            kind = msg.get_type()
            if kind == 'GLOBAL_POSITION_INT':
                pos = (msg.lat / 1e7, msg.lon / 1e7, msg.relative_alt / 1000.0, math.hypot(msg.vx, msg.vy) / 100.0)
                track.append([round(now, 1), pos[0], pos[1], round(pos[2], 2), round(pos[3], 2)])
            elif kind == 'MISSION_ITEM_REACHED' and msg.seq != 65535:
                reached.append(msg.seq)
                stamps.append(now)
                say('t=%5.1f s item %d reached at %s' % (now, msg.seq, ('%.6f, %.6f, %.0f m, %.1f m/s' % pos) if pos else '?'))
                if msg.seq in spline_targets and spline_targets[msg.seq] and pos:
                    off = metres(pos[:2], spline_targets[msg.seq])
                    check('spline item %d reached within 6 m' % msg.seq, off <= 6.0, '%.1f m' % off)
            elif kind == 'STATUSTEXT':
                say('t=%5.1f s vehicle: %s' % (now, msg.text))
                if mission.reached_command(msg.text) is not None:
                    said.append(mission.reached_command(msg.text))
                    said_at.append(now)
            elif kind == 'HEARTBEAT' and msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                if last_hb is not None and flight.is_armed(last_hb) != flight.is_armed(msg):
                    say('t=%5.1f s heartbeat: %s' % (now, 'ARMED' if flight.is_armed(msg) else 'DISARMED'))
                last_hb = msg
                if not flight.is_armed(msg) and now > 20:
                    break
        say('MISSION_ITEM_REACHED sequence: %s; vehicle text "Reached command #": %s' % (reached, said))
        check('the vehicle disarmed by itself', last_hb is not None and not flight.is_armed(last_hb))
        if name == 'loiter-speed':
            check('the vehicle reported commands 3, 4 and 6 reached, in order (takeoff and the DO commands are not announced this way)', said == [3, 4, 6], said)
            check('MISSION_ITEM_REACHED numbered them 2, 3, 5, 6: the index of the item that followed each takeoff / loiter (recorded, see the trace)', reached == [2, 3, 5, 6], reached)
            if said == [3, 4, 6]:
                i3, i4, i6 = said_at
                say('item 3 reached %.1f s; item 4 reached %.1f s; item 6 reached %.1f s' % (i3, i4, i6))
                check('items 3 to 4 (60 m at 2 m/s plus a 10 s loiter) took 35 s or more', i4 - i3 >= 35.0, '%.1f s' % (i4 - i3))
                check('items 4 to 6 (60 m after the speed was set to 8 m/s) took under 20 s', i6 - i4 < 20.0, '%.1f s' % (i6 - i4))
            if pos:
                off = metres(pos[:2], at(0, 30))
                check('the LAND ended within 5 m of its coordinates (30 m east of home, not at home)', off <= 5.0, '%.1f m from the LAND point, %.1f m from home' % (off, metres(pos[:2], HOME[:2])))
            loiter = [t for t in track if t[0] > 0]
            check('a hold of about 10 s occurred at the loiter point (speed under 0.5 m/s for 8 s or more at 20 m)', hold_seconds(track) >= 8.0, '%.1f s' % hold_seconds(track))
        elif name == 'jump-loop':
            want = [1, 2, 3, 2, 3, 2, 3, 5]
            check('the loop ran three times (items 2 and 3, jumped back twice) and then the RTL: %s' % want, reached == want, reached)
        elif name == 'spline':
            check('items 1 to 4 reached in order', [r for r in reached if r in (1, 2, 3, 4)] == [1, 2, 3, 4], reached)
            if pos:
                check('came back to within 5 m of home', metres(pos[:2], HOME[:2]) <= 5.0, '%.1f m' % metres(pos[:2], HOME[:2]))
    except Exception as e:                                   # keep the failure as the record
        check('shape finished without an exception', False, repr(e))
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
    return lines, failed, track


def hold_seconds(track):
    """Longest stretch (seconds) at 15 m or more with ground speed under 0.5 m/s."""
    best, begin = 0.0, None
    for t, lat, lon, alt, speed in track:
        if alt >= 15.0 and speed < 0.5:
            begin = t if begin is None else begin
            best = max(best, t - begin)
        else:
            begin = None
    return best


def main():
    os.makedirs(OUT, exist_ok=True)
    chosen = sys.argv[3:] or list(shapes())
    results = []
    for name in chosen:
        items, targets = shapes()[name]
        lines, failed, track = run(name, items, targets)
        lines.append('RESULT %s' % ('passed' if not failed else '%d checks failed: %s' % (len(failed), '; '.join(failed))))
        with open(os.path.join(OUT, name + '.txt'), 'w') as f:
            f.write('\n'.join(lines) + '\n')
        with open(os.path.join(OUT, name + '-track.csv'), 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['seconds', 'lat', 'lon', 'relative_alt_m', 'ground_speed_ms'])
            w.writerows(track)
        results.append((name, not failed))
        print('SHAPE %s %s' % (name, 'passed' if not failed else 'FAILED'), flush=True)
    return 0 if all(ok for _, ok in results) else 1


if __name__ == '__main__':
    sys.exit(main())
