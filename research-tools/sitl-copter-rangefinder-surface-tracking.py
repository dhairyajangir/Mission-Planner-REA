"""First direct fault-injection test of AP_RangeFinder on a flying Copter (previously only its own gtest programs - no flight, no integration). ALT_HOLD mode
calls Copter::SurfaceTracking::update_surface_offset() every loop (ArduCopter/mode_althold.cpp, ArduCopter/surface_tracking.cpp): while the downward rangefinder
is healthy it blends the position controller's altitude target toward the measured ground distance; once it goes unhealthy for more than
SURFACE_TRACKING_TIMEOUT_MS (1000ms, ArduCopter/config.h), the offset resets to 0 and the vehicle is expected to fall back to its EKF/baro altitude reference
without a bump.

Enables RNGFND1 as a SITL analog rangefinder (TYPE=1, matching ArduPilot's own copter-optflow.parm reference config), takes off in GUIDED to 20m, switches to
ALT_HOLD with centred RC_CHANNELS_OVERRIDE sticks (throttle at the deadzone midpoint holds the current altitude), then mid-flight lowers RNGFND1_MAX below the
current altitude - a clean config-only fault that makes the rangefinder report out-of-range without touching source or gdb - and watches whether the vehicle's
relative altitude stays stable through the transition instead of jumping or falling. Simulator only.

    python3 sitl-copter-rangefinder-surface-tracking.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
import csv
import os
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
WORK = os.path.expanduser('~/cg-copter-rangefinder-surface-tracking')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
TABLE = 'copter'
TAKEOFF_ALT_M = 20.0


def pump_with_sticks(conn, secs, notes, track):
    t0 = time.time()
    while time.time() - t0 < secs:
        conn.mav.rc_channels_override_send(conn.target_system, conn.target_component, 1500, 1500, 1500, 1500, 0, 0, 0, 0)
        msg = conn.recv_match(type=['GLOBAL_POSITION_INT', 'RANGEFINDER', 'STATUSTEXT'], blocking=True, timeout=0.2)
        if msg is None:
            continue
        kind = msg.get_type()
        if kind == 'STATUSTEXT':
            notes.append('vehicle: %s' % msg.text)
        elif kind == 'GLOBAL_POSITION_INT':
            track.append([round(time.time() - t0, 2), msg.relative_alt / 1000.0, msg.vz / 100.0, None])
        elif kind == 'RANGEFINDER' and track:
            track[-1][3] = msg.distance


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arducopter'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    notes, track = [], []
    proc = subprocess.Popen([BIN, '-w', '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME],
                            cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        time.sleep(30)
        base = link.read_params(conn)
        want = {'RNGFND1_TYPE': 1.0, 'RNGFND1_MIN': 0.0, 'RNGFND1_MAX': 40.0, 'RNGFND1_PIN': 0.0, 'RNGFND1_SCALING': 12.12}
        bad = [r.name for r in params.write(conn, [params.Change(n, base.get(n), v) for n, v in want.items()]) if not r.ok]
        notes.append('set %s; rejected %s; restarting under the new setting' % (want, bad))
        time.sleep(2)
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
        proc = subprocess.Popen([BIN, '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME],
                                cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)
        conn, _ = link.connect(5760, timeout=180.0)
        time.sleep(30)
        after = link.read_params(conn)
        notes.append('after restart: RNGFND1_TYPE=%s RNGFND1_MAX=%s' % (after.get('RNGFND1_TYPE'), after.get('RNGFND1_MAX')))
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 33, 100000, 0, 0, 0, 0, 0)  # GLOBAL_POSITION_INT 10Hz
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 173, 100000, 0, 0, 0, 0, 0)  # RANGEFINDER 10Hz

        flight.set_mode(conn, 'GUIDED', table=TABLE)
        armed = flight.arm(conn, timeout=120.0)
        notes.append('arm: %s' % armed.detail)
        if armed.ok:
            conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, TAKEOFF_ALT_M)
            conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
            time.sleep(25.0)

            ah = flight.set_mode(conn, 'ALT_HOLD', table=TABLE)
            notes.append('ALT_HOLD: %s' % ah.detail)
            notes.append('--- baseline, rangefinder healthy, 15s ---')
            pump_with_sticks(conn, 15.0, notes, track)

            bad2 = [r.name for r in params.write(conn, [params.Change('RNGFND1_MAX', 40.0, 1.0)]) if not r.ok]
            notes.append('--- fault: RNGFND1_MAX -> 1.0 (below current altitude, forces out-of-range) rejected %s ---' % bad2)
            pump_with_sticks(conn, 25.0, notes, track)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    with open(os.path.join(OUT, 'rangefinder-surface-tracking-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    with open(os.path.join(OUT, 'rangefinder-surface-tracking-track.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['seconds_in_phase', 'relative_alt_m', 'vz_ms', 'rangefinder_distance_m'])
        w.writerows(track)
    print('[rangefinder-surface-tracking] %d track rows; last 5: %s' % (len(track), track[-5:]), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
