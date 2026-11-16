"""First direct test of proximity-based obstacle avoidance (AC_Avoid's AC_AVOID_USE_PROXIMITY_SENSOR bit, on by default in AVOID_ENABLE's AC_AVOID_DEFAULT) rather than
relying on an ArduPilot autotest name match. AP_Proximity_SITL (PRX1_TYPE=10, an AP_PARAM_FLAG_ENABLE parameter, two-stage reboot) reports distance to the loaded
inclusion-fence polygon boundary as if it were a physical obstacle ring (AP_Proximity_SITL.cpp reads AC_Fence's own polyfence). FENCE_ACTION is left at 0 (report only,
no breach action) specifically to isolate the soft AVOID_MARGIN-based braking (default 2 m) from the fence's own hard breach response - this tests whether a simulated
proximity sensor alone can stop the vehicle short of a boundary while it is being commanded to fly straight through it.

    python3 sitl-copter-avoid-proximity.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
import json
import math
import os
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link, mission, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(HOME[0]))
WORK = os.path.expanduser('~/cg-copter-avoid-proximity')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
FENCE_NORTH_M = 30.0   # the fence's north edge, this far ahead of home


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
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        time.sleep(20)
        base = link.read_params(conn)
        want = {'PRX1_TYPE': 10.0, 'FENCE_ENABLE': 1.0, 'FENCE_TYPE': 2.0, 'FENCE_ACTION': 0.0, 'FENCE_ALT_MAX': 100.0}
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
        time.sleep(20)
        after = link.read_params(conn)
        notes.append('after restart: PRX1_TYPE=%s AVOID_ENABLE=%s FENCE_ENABLE=%s FENCE_ACTION=%s' %
                      (after.get('PRX1_TYPE'), after.get('AVOID_ENABLE'), after.get('FENCE_ENABLE'), after.get('FENCE_ACTION')))
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 33, 200000, 0, 0, 0, 0, 0)

        n_edge = HOME[0] + FENCE_NORTH_M / M_LAT
        s_edge = HOME[0] - 100.0 / M_LAT
        w_edge = HOME[1] - 100.0 / M_LON
        e_edge = HOME[1] + 100.0 / M_LON
        vertices = [(n_edge, w_edge), (n_edge, e_edge), (s_edge, e_edge), (s_edge, w_edge)]
        up = mission.upload(conn, mission.fence_polygon(vertices), mission_type=mission.FENCE)
        notes.append('fence upload ack %s (north edge %.0f m ahead)' % (up, FENCE_NORTH_M))

        guided = flight.set_mode(conn, 'GUIDED')
        retry = time.time() + 60.0
        while not guided.ok and time.time() < retry:
            time.sleep(3)
            guided = flight.set_mode(conn, 'GUIDED')
        notes.append('GUIDED: %s' % guided.detail)
        armed = flight.arm(conn, timeout=150.0)
        notes.append('arm: %s' % armed.detail)
        if armed.ok and guided.ok:
            conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, 10.0)
            begin = time.time()
            reached = False
            while time.time() - begin < 40.0:
                msg = conn.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=1)
                if msg and msg.relative_alt / 1000.0 >= 9.0:
                    reached = True
                    break
            notes.append('reached takeoff altitude: %s, after %.0f s' % (reached, time.time() - begin))

            # fly north at 5 m/s via SET_POSITION_TARGET_LOCAL_NED velocity-only, continuously, straight at/through the fence
            type_mask = 0b0000111111000111  # ignore position and acceleration, use velocity only
            start_t, last_mode = time.time(), None
            while time.time() - start_t < 45.0:
                conn.mav.set_position_target_local_ned_send(0, conn.target_system, conn.target_component, 1, type_mask, 0, 0, 0, 5.0, 0, 0, 0, 0, 0, 0, 0)
                msg = conn.recv_match(type=['GLOBAL_POSITION_INT', 'STATUSTEXT', 'HEARTBEAT'], blocking=True, timeout=0.2)
                if msg is None:
                    continue
                now = time.time() - start_t
                kind = msg.get_type()
                if kind == 'STATUSTEXT':
                    notes.append('t=%5.1f s vehicle: %s' % (now, msg.text))
                elif kind == 'HEARTBEAT' and msg.get_srcComponent() == 1:
                    mode = flight.mode_name(msg.custom_mode)
                    if mode != last_mode:
                        notes.append('t=%5.1f s mode: %s' % (now, mode))
                        last_mode = mode
                elif kind == 'GLOBAL_POSITION_INT' and msg.get_srcComponent() == 1:
                    dist_to_edge = (n_edge - msg.lat / 1e7) * M_LAT
                    speed_ms = math.hypot(msg.vx, msg.vy) / 100.0
                    track.append([round(now, 1), msg.lat / 1e7, round(dist_to_edge, 2), round(speed_ms, 2)])
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        try:
            proc.wait(60)
        except Exception:
            proc.kill()
    with open(os.path.join(OUT, 'avoid-proximity-result.json'), 'w') as f:
        json.dump({'notes': notes, 'track': track}, f, indent=1)
    closest = min((row[2] for row in track), default=None)
    print('[avoid-proximity] closest approach to fence edge: %s m' % closest, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
