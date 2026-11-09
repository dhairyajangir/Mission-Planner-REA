"""Geofence and rally points of the prototype against one disposable Copter simulator (WSL, ArduPilot SITL, pymavlink). Simulator only.

Part A: upload, download, verify and clear a polygon fence (mission type 1) and rally points (mission type 2), and read FENCE_TOTAL and RALLY_TOTAL back from the vehicle.
Part B: enable the fence, upload a mission whose first waypoint lies outside the polygon, fly it in AUTO and record what the vehicle reports and does at the breach.

    python3 run_fence_rally.py <ardupilot tree> <out dir>

The polygon is a square of +-60 m around home; the first waypoint is 78 m north of home (outside). Two rally points are stored inside the square. What the vehicle does at the breach
(mode, where it ends up) is recorded and only partly judged: the checks are that the breach is reported, the mode leaves AUTO, and the vehicle lands and disarms.
"""
import csv
import math
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from customgcs import flight, link, mission, params  # noqa: E402

TREE, OUT = sys.argv[1], sys.argv[2]
HOME = (-35.363261, 149.165230, 584.0)
LINES, FAILED = [], []
HALF_SIDE_DEG_LAT, HALF_SIDE_DEG_LON = 0.00054, 0.00066          # about 60 m each way at this latitude
RALLY = [(HOME[0] + 0.00040, HOME[1] + 0.00030, 20.0), (HOME[0] - 0.00030, HOME[1] - 0.00030, 25.0)]


def say(text=''):
    print(text, flush=True)
    LINES.append(text)


def check(label, ok, seen=''):
    say('%-4s %s%s' % ('OK' if ok else 'FAIL', label, ('   [' + str(seen) + ']') if seen != '' else ''))
    if not ok:
        FAILED.append(label)


def metres(lat1, lon1, lat2, lon2):
    return math.hypot((lat2 - lat1) * 111320.0, (lon2 - lon1) * 111320.0 * math.cos(math.radians(lat1)))


def wp(seq, command, x, y, z, frame=3):
    return mission.Item(seq, frame, command, 1 if seq == 1 else 0, 1, 0.0, 0.0, 0.0, 0.0, x, y, z)


def part_a(conn):
    say('== lists')
    square = mission.fence_polygon([(HOME[0] + HALF_SIDE_DEG_LAT, HOME[1] - HALF_SIDE_DEG_LON), (HOME[0] + HALF_SIDE_DEG_LAT, HOME[1] + HALF_SIDE_DEG_LON),
                                    (HOME[0] - HALF_SIDE_DEG_LAT, HOME[1] + HALF_SIDE_DEG_LON), (HOME[0] - HALF_SIDE_DEG_LAT, HOME[1] - HALF_SIDE_DEG_LON)])
    rally = mission.rally_points(RALLY)
    check('fence polygon uploaded (ack 0)', mission.upload(conn, square, mission_type=mission.FENCE) == 0)
    got = mission.download(conn, mission_type=mission.FENCE)
    check('fence downloads back equal (4 vertices)', len(got) == 4 and mission.verify(square, got, skip_home=False) == [], mission.verify(square, got, skip_home=False)[:3])
    check('rally points uploaded (ack 0)', mission.upload(conn, rally, mission_type=mission.RALLY) == 0)
    got = mission.download(conn, mission_type=mission.RALLY)
    check('rally points download back equal (2 points)', len(got) == 2 and mission.verify(rally, got, skip_home=False) == [], mission.verify(rally, got, skip_home=False)[:3])
    time.sleep(1)
    now = link.read_params(conn)
    # AC_PolyFence_loader.cpp:1278 stores total_vertex_count + 2 (a return point and a closing point) in FENCE_TOTAL, so a four-vertex polygon reads 6
    check('vehicle reports FENCE_TOTAL 6 (4 vertices + return and closing point) and RALLY_TOTAL 2', now.get('FENCE_TOTAL') == 6 and now.get('RALLY_TOTAL') == 2, (now.get('FENCE_TOTAL'), now.get('RALLY_TOTAL')))
    check('mission list untouched by the other two lists', mission.download(conn, mission_type=mission.MISSION) == [] or len(mission.download(conn, mission_type=mission.MISSION)) <= 1)
    check('rally clear accepted and list empty', mission.clear(conn, mission_type=mission.RALLY) == 0 and mission.download(conn, mission_type=mission.RALLY) == [])
    check('rally points re-uploaded', mission.upload(conn, rally, mission_type=mission.RALLY) == 0)
    return square


def part_b(conn):
    say('== fence breach in flight')
    base = link.read_params(conn)
    changes = [params.Change('FENCE_ENABLE', base['FENCE_ENABLE'], 1.0), params.Change('FENCE_ACTION', base['FENCE_ACTION'], 1.0)]
    check('fence enabled with action 1 (RTL or land)', all(r.ok for r in params.write(conn, changes)))
    north = HOME[0] + 0.0007
    east = HOME[1] + 0.0009
    items = [wp(0, 16, HOME[0], HOME[1], HOME[2], frame=0), wp(1, 22, 0.0, 0.0, 15.0), wp(2, 16, north, HOME[1], 15.0), wp(3, 16, north, east, 15.0), wp(4, 20, 0.0, 0.0, 0.0)]
    check('mission uploaded', mission.upload(conn, items) == 0)
    flight.set_mode(conn, 'STABILIZE')
    armed = flight.arm(conn, timeout=150.0)
    check('armed', armed.ok, armed.detail)
    if not armed.ok:
        return
    auto = flight.set_mode(conn, 'AUTO')
    retry = time.time() + 90.0
    while not auto.ok and time.time() < retry:
        time.sleep(3)
        auto = flight.set_mode(conn, 'AUTO')
    check('AUTO accepted', auto.ok, auto.detail)
    if not auto.ok:
        return
    say('     mission start: %s' % flight.start_mission(conn).detail)
    track, reached, texts, modes = [], [], [], []
    pos, last_hb, start = None, None, time.time()
    while time.time() - start < 300.0:
        msg = conn.recv_match(type=['MISSION_ITEM_REACHED', 'GLOBAL_POSITION_INT', 'HEARTBEAT', 'STATUSTEXT'], blocking=True, timeout=1)
        if msg is None:
            continue
        kind = msg.get_type()
        if kind == 'GLOBAL_POSITION_INT':
            pos = (msg.lat / 1e7, msg.lon / 1e7, msg.relative_alt / 1000.0)
            track.append([round(time.time() - start, 1), pos[0], pos[1], round(pos[2], 2), flight.mode_name(last_hb.custom_mode) if last_hb else ''])
        elif kind == 'MISSION_ITEM_REACHED' and msg.seq != 65535:
            reached.append(msg.seq)
            say('     t=%5.1f s item %d reached' % (time.time() - start, msg.seq))
        elif kind == 'STATUSTEXT':
            texts.append(msg.text)
            say('     t=%5.1f s vehicle: %s' % (time.time() - start, msg.text))
        elif kind == 'HEARTBEAT' and msg.get_srcComponent() == 1 and msg.type not in (6, 27):
            if last_hb is None or last_hb.custom_mode != msg.custom_mode or flight.is_armed(last_hb) != flight.is_armed(msg):
                modes.append(flight.mode_name(msg.custom_mode))
                say('     t=%5.1f s heartbeat: %s, mode %s' % (time.time() - start, 'ARMED' if flight.is_armed(msg) else 'DISARMED', flight.mode_name(msg.custom_mode)))
            last_hb = msg
            if not flight.is_armed(msg) and time.time() - start > 20:
                break
    with open(os.path.join(OUT, 'fence-flight-track.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['seconds', 'lat', 'lon', 'relative_alt_m', 'mode'])
        w.writerows(track)
    breach = [t for t in texts if 'ence' in t]
    check('the vehicle reported the fence breach', any('breach' in t.lower() for t in breach), breach[:3])
    check('the mode left AUTO after the breach', any(m not in ('AUTO', 'STABILIZE') for m in modes), modes)
    check('waypoint 2 (outside the fence) was not reported reached', 2 not in reached, reached)
    check('the vehicle disarmed by itself', last_hb is not None and not flight.is_armed(last_hb))
    if pos:
        say('     last position %.1f m from home, %.1f m from rally point 1, %.1f m from rally point 2' % (metres(pos[0], pos[1], HOME[0], HOME[1]), metres(pos[0], pos[1], RALLY[0][0], RALLY[0][1]),
                                                                                                             metres(pos[0], pos[1], RALLY[1][0], RALLY[1][1])))
        inside = abs(pos[0] - HOME[0]) <= HALF_SIDE_DEG_LAT and abs(pos[1] - HOME[1]) <= HALF_SIDE_DEG_LON
        check('the vehicle ended inside the fence', inside, '%.6f, %.6f' % (pos[0], pos[1]))


def main():
    os.makedirs(OUT, exist_ok=True)
    work = os.path.expanduser('~/cg-fence')
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
        for part in (part_a, part_b):
            try:
                part(conn)
            except Exception as e:                       # keep the failure as the record
                check('%s finished without an exception' % part.__name__, False, repr(e))
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
    say('')
    say('RESULT %s' % ('all checks passed' if not FAILED else '%d checks failed: %s' % (len(FAILED), '; '.join(FAILED))))
    with open(os.path.join(OUT, 'fence-rally-run.txt'), 'w') as f:
        f.write('\n'.join(LINES) + '\n')
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
