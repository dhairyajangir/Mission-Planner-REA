"""Fault injection follow-up to ledger:heli-flight-and-autorotation (already confirmed: AUTOROTATE mode can be manually selected and glides down under control). That test never
injected an actual engine failure - it only requested AUTOROTATE directly. Source reading (ArduCopter/heli.cpp, AC_Autorotation.cpp) found no automatic engine-failure detector
that switches a helicopter into AUTOROTATE by itself: heli.cpp's heli_update_autorotation() only reacts to the motor INTERLOCK switch being off, and AC_Autorotation.cpp is purely
the controller used once in that mode, with no RPM-loss-triggered mode change anywhere. This flies the heli normally (reusing sitl-heli-flight.py's launch/arm/interlock recipe),
then - staying in the SAME flight mode, never requesting AUTOROTATE - injects SIM_ENGINE_FAIL on the frame's real motor channel (read live from SERVOx_FUNCTION rather than assumed,
the same lesson learned from the QuadPlane motor-failure correction elsewhere in this project), to see whether anything automatic happens or the aircraft simply falls.

    python3 sitl-heli-engine-failure.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
import json
import os
import subprocess
import sys
import threading
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link, mission, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
WORK = os.path.expanduser('~/cg-heli-engine-failure')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter-heli')
K_MOTOR1 = 33


class Sticks(threading.Thread):
    def __init__(self, conn):
        super().__init__(daemon=True)
        self.conn, self.collective, self.interlock, self.running = conn, 1000, 1000, True

    def run(self):
        while self.running:
            try:
                self.conn.mav.rc_channels_override_send(self.conn.target_system, self.conn.target_component, 1500, 1500, self.collective, 1500, 0, 0, 0, self.interlock)
            except Exception:
                pass
            time.sleep(0.1)


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    proc = subprocess.Popen([BIN, '-w', '--model', 'heli', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                            stdout=open(os.path.join(WORK, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    notes, sticks = [], None
    try:
        conn, _ = link.connect(5760, timeout=600.0)
        time.sleep(60)
        p = link.read_params(conn)
        servo_functions = {ch: p.get('SERVO%d_FUNCTION' % ch) for ch in range(1, 9)}
        motor_channels = [ch for ch, fn in servo_functions.items() if fn == K_MOTOR1]
        notes.append('SERVOx_FUNCTION: %s; k_motor1 (33) on channel(s): %s' % (servo_functions, motor_channels))
        if not motor_channels:
            notes.append('no k_motor1 channel found, cannot target SIM_ENGINE_FAIL correctly, aborting')
            raise RuntimeError('no motor channel found')
        engine_fail_bit = 1 << (motor_channels[0] - 1)

        sticks = Sticks(conn)
        sticks.start()
        items = [mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2]), mission.Item(1, 3, 22, 1, 1, 0, 0, 0, 0, 0.0, 0.0, 30.0),
                 mission.Item(2, 3, 19, 0, 1, 600.0, 0, 0, 0, HOME[0] + 40 / M_LAT, HOME[1], 30.0)]
        notes.append('upload ack %s' % mission.upload(conn, items))
        notes.append('STABILIZE: %s' % flight.set_mode(conn, 'STABILIZE').detail)
        armed = flight.arm(conn, timeout=150.0)
        notes.append('arm (interlock switch low): %s' % armed.detail)
        if armed.ok:
            sticks.interlock = 2000
            notes.append('interlock switch raised')
            time.sleep(25.0)
            auto = flight.set_mode(conn, 'AUTO')
            notes.append('AUTO: %s' % auto.detail)
            notes.append('start: %s' % flight.start_mission(conn).detail)
            sticks.collective = 1500

            start_t = time.time()
            injected = False
            while time.time() - start_t < 120.0:
                msg = conn.recv_match(type=['STATUSTEXT', 'HEARTBEAT'], blocking=True, timeout=1)
                if msg is None:
                    continue
                now = time.time() - start_t
                if msg.get_type() == 'STATUSTEXT':
                    notes.append('t=%5.1f s vehicle: %s' % (now, msg.text))
                elif msg.get_type() == 'HEARTBEAT' and msg.get_srcComponent() == 1:
                    if not injected and now > 20.0:
                        injected = True
                        bad = [r.name for r in params.write(conn, [params.Change('SIM_ENGINE_FAIL', 0.0, float(engine_fail_bit))]) if not r.ok]
                        notes.append('t=%5.1f s fault injected SIM_ENGINE_FAIL=%d (channel %d, bit %d) (rejected %s), mode left unchanged (no AUTOROTATE requested)'
                                     % (now, engine_fail_bit, motor_channels[0], motor_channels[0] - 1, bad))
                    if not flight.is_armed(msg) and now > 25.0:
                        notes.append('t=%5.1f s disarmed, stopping watch' % now)
                        break
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        if sticks:
            sticks.running = False
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter-heli'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    with open(os.path.join(OUT, 'heli-engine-failure-notes.json'), 'w') as f:
        json.dump({'notes': notes}, f, indent=1)
    print('[heli-engine-failure] done, %d notes' % len(notes), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
