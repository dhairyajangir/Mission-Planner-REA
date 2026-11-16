"""Fault injection / first real test of ledger:swarm-control, which so far is "PID numerics only; no multi-vehicle SITL, no GUI." AP_Follow (FOLLOW mode) consumes
GLOBAL_POSITION_INT from a target sysid (FOLL_SYSID) - libraries/AP_Follow/AP_Follow.cpp's handle_global_position_int_message(). Rather than a second full SITL
instance, this synthesizes a moving "leader" by sending GLOBAL_POSITION_INT from a different sysid over the same MAVLink link, and watches whether a real Copter in
FOLLOW mode actually tracks it - the first time this project has exercised AP_Follow against a live vehicle rather than PID numerics alone. FOLL_ENABLE is an
AP_PARAM_FLAG_ENABLE parameter, so the usual two-stage reboot is used.

    python3 sitl-copter-follow.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
import json
import math
import os
import subprocess
import sys
import threading
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(HOME[0]))
WORK = os.path.expanduser('~/cg-copter-follow')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
LEADER_SYSID = 2
LEADER_SPEED_MS = 2.0          # leader moves north at this speed once the test starts
LEADER_START_OFFSET_M = 15.0   # leader starts this far north of home


def metres(lat1, lon1, lat2, lon2):
    return math.hypot((lat2 - lat1) * M_LAT, (lon2 - lon1) * M_LON)


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arducopter'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    notes, track = [], []
    proc = subprocess.Popen([BIN, '-w', '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                            stdout=open(os.path.join(WORK, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    stop = {'on': True}
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        my_sysid = conn.mav.srcSystem
        time.sleep(20)
        base = link.read_params(conn)
        want = {'FOLL_ENABLE': 1.0, 'FOLL_SYSID': float(LEADER_SYSID), 'FOLL_OFS_X': 0.0, 'FOLL_OFS_Y': 0.0, 'FOLL_OFS_Z': 0.0, 'FOLL_DIST_MAX': 100.0}
        bad = [r.name for r in params.write(conn, [params.Change(n, base.get(n), v) for n, v in want.items()]) if not r.ok]
        notes.append('set %s; rejected %s; restarting under the new setting' % (want, bad))
        time.sleep(2)
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
        proc = subprocess.Popen([BIN, '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                                stdout=open(os.path.join(WORK, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)
        conn, _ = link.connect(5760, timeout=180.0)
        my_sysid = conn.mav.srcSystem
        time.sleep(20)
        after = link.read_params(conn)
        notes.append('after restart: FOLL_ENABLE=%s FOLL_SYSID=%s' % (after.get('FOLL_ENABLE'), after.get('FOLL_SYSID')))
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 33, 200000, 0, 0, 0, 0, 0)  # GLOBAL_POSITION_INT at 5 Hz (not streamed by default)

        leader_start = (HOME[0] + LEADER_START_OFFSET_M / M_LAT, HOME[1])
        start_time = [None]

        def leader():
            t0 = time.time()
            while stop['on']:
                now = time.time() - t0
                moved = max(0.0, now - 10.0) * LEADER_SPEED_MS if start_time[0] is not None else 0.0
                lat = leader_start[0] + moved / M_LAT
                lon = leader_start[1]
                conn.mav.srcSystem = LEADER_SYSID
                conn.mav.global_position_int_send(int(time.time() * 1000) & 0xFFFFFFFF, int(lat * 1e7), int(lon * 1e7),
                                                   int(20.0 * 1000), int(20.0 * 1000), 0, 0, 0, 0)
                conn.mav.srcSystem = my_sysid
                conn.mav.heartbeat_send(6, 8, 0, 0, 0)
                time.sleep(0.5)
        threading.Thread(target=leader, daemon=True).start()
        time.sleep(3)

        guided = flight.set_mode(conn, 'GUIDED')
        retry = time.time() + 60.0
        while not guided.ok and time.time() < retry:
            time.sleep(3)
            guided = flight.set_mode(conn, 'GUIDED')
        notes.append('GUIDED (pre-arm): %s' % guided.detail)
        armed = flight.arm(conn, timeout=150.0)
        notes.append('arm: %s' % armed.detail)
        if armed.ok and guided.ok:
            conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, 20.0)
            begin, reached, last_mode = time.time(), False, None
            while time.time() - begin < 40.0:
                msg = conn.recv_match(type=['GLOBAL_POSITION_INT', 'HEARTBEAT', 'STATUSTEXT'], blocking=True, timeout=1)
                if msg is None:
                    continue
                kind = msg.get_type()
                if kind == 'STATUSTEXT':
                    notes.append('t=%5.1f s (takeoff) vehicle: %s' % (time.time() - begin, msg.text))
                elif kind == 'HEARTBEAT' and msg.get_srcComponent() == 1:
                    mode = flight.mode_name(msg.custom_mode)
                    if (mode, flight.is_armed(msg)) != last_mode:
                        notes.append('t=%5.1f s (takeoff) mode: %s (armed=%s)' % (time.time() - begin, mode, flight.is_armed(msg)))
                        last_mode = (mode, flight.is_armed(msg))
                elif kind == 'GLOBAL_POSITION_INT' and msg.get_srcComponent() == 1:
                    if msg.relative_alt / 1000.0 >= 18.0:
                        reached = True
                        break
            notes.append('reached takeoff altitude: %s, after %.0f s' % (reached, time.time() - begin))
            notes.append('FOLLOW: %s' % flight.set_mode(conn, 'FOLLOW').detail)
            start_time[0] = time.time()

            watch_start, last_mode = time.time(), None
            while time.time() - watch_start < 60.0:
                msg = conn.recv_match(type=['GLOBAL_POSITION_INT', 'HEARTBEAT', 'STATUSTEXT'], blocking=True, timeout=1)
                if msg is None:
                    continue
                now = time.time() - watch_start
                kind = msg.get_type()
                if kind == 'STATUSTEXT':
                    notes.append('t=%5.1f s vehicle: %s' % (now, msg.text))
                    continue
                if kind == 'HEARTBEAT' and msg.get_srcComponent() == 1:
                    mode = flight.mode_name(msg.custom_mode)
                    if mode != last_mode:
                        notes.append('t=%5.1f s mode: %s (armed=%s)' % (now, mode, flight.is_armed(msg)))
                        last_mode = mode
                    continue
                if kind == 'GLOBAL_POSITION_INT' and msg.get_srcComponent() == 1:
                    moved = max(0.0, (time.time() - start_time[0]) - 10.0) * LEADER_SPEED_MS
                    leader_lat = leader_start[0] + moved / M_LAT
                    dist = metres(msg.lat / 1e7, msg.lon / 1e7, leader_lat, leader_start[1])
                    track.append([round(now, 1), msg.lat / 1e7, msg.lon / 1e7, round(dist, 1)])
                    if len(track) % 10 == 0:
                        notes.append('t=%5.1f s distance to leader %.1f m' % (now, dist))
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        stop['on'] = False
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        try:
            proc.wait(60)
        except Exception:
            proc.kill()
    with open(os.path.join(OUT, 'follow-result.json'), 'w') as f:
        json.dump({'notes': notes, 'track': track}, f, indent=1)
    print('[copter-follow] %s' % notes[-3:], flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
