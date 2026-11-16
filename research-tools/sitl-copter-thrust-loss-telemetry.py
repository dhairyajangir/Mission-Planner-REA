"""Follow-up to sitl-copter-motor-failure.py and sitl-motor-failure-angle-gdb.py. Those two established that Copter::thrust_loss_check's warning fired 1.8s
*after* ground impact at 30m and never fired at all at 100m, and proposed (from source alone, crash_check.cpp) that the detector's own counter-reset guards -
desired lean angle over 15 degrees, throttle under 90% (unless saturated), throttle under 25%, no positive descent-rate estimate, or actual attitude error
over 30 degrees - were suppressing it during exactly the tumbling a lost motor causes. A gdb confirmation attempt failed (the same "copter has unknown type"
expression-evaluation wall documented elsewhere in this project).

This sidesteps gdb entirely: it replays the same 30m single-motor-failure fault (SIM_ENGINE_FAIL) while requesting ATTITUDE (actual roll/pitch),
NAV_CONTROLLER_OUTPUT (nav_roll/nav_pitch - the attitude controller's own commanded lean angles, the real proxy for "desired angle target"), and VFR_HUD
(throttle %, climb rate) at 20Hz over MAVLink, so the five crash_check.cpp reset gates can be reconstructed directly from telemetry instead of guessed at,
and checked against exactly when (or whether) "Potential Thrust Loss" actually appears. Simulator only.

    python3 sitl-copter-thrust-loss-telemetry.py <ardupilot tree> <out dir> <custom-gcs dir> [takeoff_alt_m]
"""
import csv
import os
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
TAKEOFF_ALT_M = float(sys.argv[4]) if len(sys.argv) > 4 else 30.0
sys.path.insert(0, GCS)
from customgcs import flight, link, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
WORK = os.path.expanduser('~/cg-copter-thrust-loss-telemetry')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arducopter'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    notes, track = [], []
    latest = {'roll_deg': None, 'pitch_deg': None, 'nav_roll_deg': None, 'nav_pitch_deg': None,
              'throttle_pct': None, 'climb_ms': None}
    proc = subprocess.Popen([BIN, '-w', '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME],
                            cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        for msg_id, hz in ((33, 10.0), (30, 20.0), (62, 20.0), (74, 20.0)):
            conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, msg_id, 1e6 / hz, 0, 0, 0, 0, 0)
        time.sleep(45)
        flight.set_mode(conn, 'GUIDED', table='copter')
        armed = flight.arm(conn, timeout=120.0)
        notes.append('arm: %s' % armed.detail)
        if armed.ok:
            conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, TAKEOFF_ALT_M)
            ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
            notes.append('takeoff to %.0f m ack %s' % (TAKEOFF_ALT_M, None if ack is None else ack.result))
            time.sleep(max(25.0, TAKEOFF_ALT_M))
            base = link.read_params(conn)
            bad = [r.name for r in params.write(conn, [params.Change('SIM_ENGINE_FAIL', base.get('SIM_ENGINE_FAIL'), 1.0)]) if not r.ok]
            notes.append('SIM_ENGINE_FAIL -> 1 (motor 1 killed, SIM_ENGINE_MUL default 0 = full loss) (rejected %s)' % bad)
            t0 = time.time()
            while time.time() - t0 < 25.0:
                msg = conn.recv_match(type=['GLOBAL_POSITION_INT', 'STATUSTEXT', 'HEARTBEAT', 'ATTITUDE', 'NAV_CONTROLLER_OUTPUT', 'VFR_HUD'],
                                       blocking=True, timeout=1)
                if msg is None:
                    continue
                t = time.time() - t0
                kind = msg.get_type()
                if kind == 'STATUSTEXT':
                    notes.append('t=%5.1f vehicle: %s' % (t, msg.text))
                elif kind == 'ATTITUDE':
                    latest['roll_deg'] = msg.roll * 57.29578
                    latest['pitch_deg'] = msg.pitch * 57.29578
                elif kind == 'NAV_CONTROLLER_OUTPUT':
                    latest['nav_roll_deg'] = msg.nav_roll
                    latest['nav_pitch_deg'] = msg.nav_pitch
                elif kind == 'VFR_HUD':
                    latest['throttle_pct'] = msg.throttle
                    latest['climb_ms'] = msg.climb
                elif kind == 'GLOBAL_POSITION_INT':
                    track.append([round(t, 2), msg.relative_alt / 1000.0, msg.vz / 100.0,
                                  latest['roll_deg'], latest['pitch_deg'], latest['nav_roll_deg'], latest['nav_pitch_deg'],
                                  latest['throttle_pct'], latest['climb_ms']])
                elif kind == 'HEARTBEAT' and msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                    notes.append('t=%5.1f armed=%s' % (t, flight.is_armed(msg)))
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    with open(os.path.join(OUT, 'thrust-loss-telemetry-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    with open(os.path.join(OUT, 'thrust-loss-telemetry-track.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['seconds', 'relative_alt_m', 'vz_ms', 'roll_deg', 'pitch_deg', 'nav_roll_deg', 'nav_pitch_deg', 'throttle_pct', 'climb_ms'])
        w.writerows(track)
    last = track[-1] if track else None
    print('[thrust-loss-telemetry] %d rows; last=%s' % (len(track), last), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
