"""Fault injection, not tried anywhere else in this project: a single motor failure on a flying multicopter, using SITL's own SIM_ENGINE_FAIL (bitmask of which motor to kill,
SIM_ENGINE_MUL defaults to 0 = full thrust loss on that motor). ArduCopter has a dedicated detector for this (Copter::thrust_loss_check, ArduCopter/crash_check.cpp): descending
despite a roughly level attitude and throttle above 90% (or saturated) for 1 full second triggers "Potential Thrust Loss (<motor>)" on the GCS and motors->set_thrust_boost(true),
which redistributes the remaining motors' thrust to compensate. Arm in GUIDED, take off to 30 m (enough margin that the climb is still using meaningful throttle), fail motor 1,
watch for the text and the reported lost-motor index, and whether the vehicle keeps flying or hits the ground. Simulator only (WSL, pymavlink, the custom-gcs library).

    python3 sitl-copter-motor-failure.py <ardupilot tree> <out dir> <custom-gcs dir>
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
WORK = os.path.expanduser('~/cg-copter-motor-failure')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')


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
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 33, 100000, 0, 0, 0, 0, 0)  # GLOBAL_POSITION_INT at 10 Hz
        time.sleep(45)
        flight.set_mode(conn, 'GUIDED', table='copter')
        armed = flight.arm(conn, timeout=120.0)
        notes.append('arm: %s' % armed.detail)
        if armed.ok:
            conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, 30.0)
            ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
            notes.append('takeoff to 30 m ack %s' % (None if ack is None else ack.result))
            time.sleep(25)  # let it stabilise in the hover before failing a motor
            base = link.read_params(conn)
            bad = [r.name for r in params.write(conn, [params.Change('SIM_ENGINE_FAIL', base.get('SIM_ENGINE_FAIL'), 1.0)]) if not r.ok]
            notes.append('SIM_ENGINE_FAIL -> 1 (motor 1 killed, SIM_ENGINE_MUL default 0 = full loss) (rejected %s)' % bad)
            t0 = time.time()
            while time.time() - t0 < 25.0:
                msg = conn.recv_match(type=['GLOBAL_POSITION_INT', 'STATUSTEXT', 'HEARTBEAT'], blocking=True, timeout=1)
                if msg is None:
                    continue
                t = time.time() - t0
                kind = msg.get_type()
                if kind == 'STATUSTEXT':
                    notes.append('t=%5.1f vehicle: %s' % (t, msg.text))
                elif kind == 'GLOBAL_POSITION_INT':
                    track.append([round(t, 1), msg.relative_alt / 1000.0, msg.vz / 100.0])
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
    with open(os.path.join(OUT, 'copter-motor-failure-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    with open(os.path.join(OUT, 'copter-motor-failure-track.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['seconds', 'relative_alt_m', 'vz_ms'])
        w.writerows(track)
    last = track[-1] if track else None
    print('[copter-motor-failure] %d rows; last alt=%s vz=%s' % (len(track), last[1] if last else None, last[2] if last else None), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
