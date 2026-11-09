"""Fly an uploaded mission on one disposable Copter simulator (WSL, ArduPilot SITL, pymavlink) and compare what the vehicle did with what was uploaded. Simulator only.

The mission: TAKEOFF to 15 m, two waypoints about 80 m north and then 80 m east of home, RETURN_TO_LAUNCH. The script arms in STABILIZE, switches to AUTO, and follows
MISSION_ITEM_REACHED, GLOBAL_POSITION_INT and HEARTBEAT until the vehicle disarms (landed after RTL) or the time limit is hit. It checks: every item reached in order, position
at each waypoint within a tolerance of the uploaded coordinates, altitude reached, return near home, and disarm. A flight track (CSV) is kept.

    python3 run_flight.py <ardupilot tree> <out dir> [speedup, default 1]
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
SPEEDUP = sys.argv[3] if len(sys.argv) > 3 else '1'      # speedup 1: the vehicle's auto-disarm timer (10 s) must not run out between arming and AUTO
HOME = (-35.363261, 149.165230, 584.0)
LINES = []
FAILED = []
WAYPOINT_TOLERANCE_M = 6.0        # the vehicle's own acceptance radius is WP_RADIUS_M (2 m in the parameters); some margin for the 10 Hz position stream
HOME_TOLERANCE_M = 5.0
TIME_LIMIT_S = 600.0              # wall-clock seconds


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


def finish(track):
    with open(os.path.join(OUT, 'flight-track.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['seconds', 'lat', 'lon', 'relative_alt_m', 'last_item_reached', 'mode'])
        w.writerows(track)
    say('')
    say('RESULT %s' % ('all checks passed' if not FAILED else '%d checks failed: %s' % (len(FAILED), '; '.join(FAILED))))
    with open(os.path.join(OUT, 'flight-run.txt'), 'w') as f:
        f.write('\n'.join(LINES) + '\n')


def main():
    os.makedirs(OUT, exist_ok=True)
    work = os.path.expanduser('~/cg-flight')
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', work])
    os.makedirs(work)
    proc = subprocess.Popen([os.path.join(TREE, 'build/sitl/bin/arducopter'), '-w', '--model', '+', '-I', '0', '-s', SPEEDUP, '--home', '%s,%s,%s,0' % HOME],
                            cwd=work, stdout=open(os.path.join(work, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    track = []
    try:
        conn, mav_type = link.connect(5760)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 33, 100000, 0, 0, 0, 0, 0)       # GLOBAL_POSITION_INT at 10 Hz
        say('connected; speedup %s' % SPEEDUP)
        time.sleep(50)                                  # GPS and the EKF origin came 18 to 41 s after start in earlier runs; AUTO needs a position
        north, east = HOME[0] + 0.0007, HOME[1] + 0.0009
        items = [wp(0, 16, HOME[0], HOME[1], HOME[2], frame=0), wp(1, 22, 0.0, 0.0, 15.0), wp(2, 16, north, HOME[1], 15.0), wp(3, 16, north, east, 15.0), wp(4, 20, 0.0, 0.0, 0.0)]
        check('mission uploaded (ack 0)', mission.upload(conn, items) == 0)
        check('mission reads back equal', mission.verify(items, mission.download(conn)) == [])
        say('     leg lengths: home to WP2 %.0f m, WP2 to WP3 %.0f m' % (metres(HOME[0], HOME[1], north, HOME[1]), metres(north, HOME[1], north, east)))
        flight.set_mode(conn, 'STABILIZE')
        armed = flight.arm(conn, timeout=150.0)
        check('armed', armed.ok, armed.detail)
        if not armed.ok:
            return
        auto = flight.set_mode(conn, 'AUTO')
        retry_until = time.time() + 90.0
        while not auto.ok and time.time() < retry_until:                # a refusal right after arming can mean the position estimate is not ready yet; try again
            time.sleep(3)
            auto = flight.set_mode(conn, 'AUTO')
        check('AUTO accepted with the mission loaded', auto.ok, auto.detail + ' | ' + '; '.join(auto.texts[-2:]))
        if not auto.ok:
            return
        started = flight.start_mission(conn)
        say('     mission start: %s' % started.detail)
        reached, texts = [], []
        start = time.time()
        last_hb = None
        pos = None
        while time.time() - start < TIME_LIMIT_S:
            msg = conn.recv_match(type=['MISSION_ITEM_REACHED', 'GLOBAL_POSITION_INT', 'HEARTBEAT', 'STATUSTEXT', 'MISSION_CURRENT'], blocking=True, timeout=1)
            if msg is None:
                continue
            kind = msg.get_type()
            if kind == 'GLOBAL_POSITION_INT':
                pos = (msg.lat / 1e7, msg.lon / 1e7, msg.relative_alt / 1000.0)
                track.append([round(time.time() - start, 1), pos[0], pos[1], round(pos[2], 2), reached[-1] if reached else '', flight.mode_name(last_hb.custom_mode) if last_hb else ''])
            elif kind == 'MISSION_ITEM_REACHED' and msg.seq != 65535:          # 65535 is not an item
                reached.append(msg.seq)
                say('     t=%5.1f s item %d reached at %s' % (time.time() - start, msg.seq, ('%.6f, %.6f, %.1f m' % pos) if pos else 'unknown position'))
                if msg.seq in (2, 3) and pos:
                    target = (north, HOME[1]) if msg.seq == 2 else (north, east)
                    check('item %d reached within %.0f m of its coordinates' % (msg.seq, WAYPOINT_TOLERANCE_M), metres(pos[0], pos[1], target[0], target[1]) <= WAYPOINT_TOLERANCE_M,
                          '%.1f m off, %.1f m up' % (metres(pos[0], pos[1], target[0], target[1]), pos[2]))
            elif kind == 'STATUSTEXT':
                texts.append(msg.text)
                say('     t=%5.1f s vehicle: %s' % (time.time() - start, msg.text))
            elif kind == 'HEARTBEAT' and msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                if last_hb is not None and flight.is_armed(last_hb) != flight.is_armed(msg):
                    say('     t=%5.1f s heartbeat: %s, mode %s' % (time.time() - start, 'ARMED' if flight.is_armed(msg) else 'DISARMED', flight.mode_name(msg.custom_mode)))
                last_hb = msg
                if not flight.is_armed(msg) and (reached or time.time() - start > 30):
                    break
        check('items reached in order', [r for r in reached if r in (1, 2, 3)] == [1, 2, 3], reached)
        peak = max((t[3] for t in track), default=0)
        check('altitude reached 14 m or more during the flight', peak >= 14.0, 'peak %.1f m' % peak)
        check('vehicle disarmed by itself after the return', last_hb is not None and not flight.is_armed(last_hb))
        if pos:
            check('last position within %.0f m of home' % HOME_TOLERANCE_M, metres(pos[0], pos[1], HOME[0], HOME[1]) <= HOME_TOLERANCE_M, '%.1f m, %.1f m up' % (metres(pos[0], pos[1], HOME[0], HOME[1]), pos[2]))
        say('     flight took %.0f s of wall-clock time at speedup %s' % (time.time() - start, SPEEDUP))
    except Exception as e:                                  # keep the failure as the record
        check('flight run finished without an exception', False, repr(e))
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
        finish(track)


if __name__ == '__main__':
    main()
    sys.exit(1 if FAILED else 0)
