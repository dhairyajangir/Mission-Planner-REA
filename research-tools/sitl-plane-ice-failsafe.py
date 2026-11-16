"""Fault injection follow-up to the already-confirmed plane-ice engine start (ledger:plane-ice-engine-start, target L3+fault, no fault yet): AP_ICEngine::update() has a
documented RC-failsafe interaction, ICE_OPTIONS bit 0 (DISABLE_IGNITION_RC_FAILSAFE) - "if (option_set(Options::DISABLE_IGNITION_RC_FAILSAFE) && AP_Notify::flags.failsafe_radio)
should_run = false", which (from ICE_RUNNING) logs "Stopped engine" (AP_ICEngine.cpp). This starts the plane-ice airframe exactly as already confirmed (RC11_OPTION 179, channel 11
held at 1900 by RC override), sets ICE_OPTIONS=1, flies an AUTO mission, then injects SIM_RC_FAIL=1 once airborne and the engine is running, and watches for the engine to actually
stop in response - the positive case the original confirmation never exercised.

    python3 sitl-plane-ice-failsafe.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
import math
import os
import subprocess
import sys
import threading
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import link, flight, mission, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
WORK = os.path.expanduser('~/cg-plane-ice-failsafe')
T = os.path.join(TREE, 'Tools/autotest')
BIN = os.path.join(TREE, 'build/sitl/bin/arduplane')
DEFAULTS = ','.join([os.path.join(T, 'models/plane.parm'), os.path.join(T, 'default_params/plane-ice.parm')])
TABLE = 'plane'
M_PER_DEG_LAT = 111320.0
LEG_DEG = 300.0 / M_PER_DEG_LAT


def route():
    a = (HOME[0] + LEG_DEG, HOME[1])
    return [mission.Item(0, 0, 16, 0, 1, 0.0, 0.0, 0.0, 0.0, HOME[0], HOME[1], HOME[2]),
            mission.Item(1, 3, 22, 1, 1, 15.0, 0.0, 0.0, 0.0, 0.0, 0.0, 60.0),
            mission.Item(2, 3, 16, 0, 1, 0.0, 0.0, 0.0, 0.0, a[0], a[1], 60.0),
            mission.Item(3, 3, 21, 0, 1, 0.0, 0.0, 0.0, 0.0, HOME[0], HOME[1], 0.0)]


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arduplane'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    notes, engine_running, engine_stopped = [], False, False
    proc = subprocess.Popen([BIN, '-w', '--model', 'plane', '--defaults', DEFAULTS, '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME],
                            cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    beat = {'on': True}
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        conn.mav.heartbeat_send(6, 8, 0, 0, 0)

        def beats():
            while beat['on']:
                try:
                    conn.mav.heartbeat_send(6, 8, 0, 0, 0)
                    conn.mav.rc_channels_override_send(conn.target_system, conn.target_component, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1900, 0, 0, 0, 0, 0, 0, 0)
                except Exception:
                    return
                time.sleep(1.0)
        threading.Thread(target=beats, daemon=True).start()
        time.sleep(50)

        base = link.read_params(conn)
        bad = [r.name for r in params.write(conn, [params.Change('ICE_OPTIONS', base.get('ICE_OPTIONS'), 1.0)]) if not r.ok]
        notes.append('ICE_OPTIONS -> 1 (disable ignition on RC failsafe) (rejected %s)' % bad)
        notes.append('RC channel 11 held at 1900 by RC override (ICE start/stop, RC11_OPTION 179 from plane-ice.parm)')

        up = mission.upload(conn, route())
        notes.append('mission upload ack %s' % up)
        flight.set_mode(conn, 'MANUAL', table=TABLE)
        armed = flight.arm(conn, timeout=150.0)
        notes.append('armed: %r' % (armed,))
        if armed.ok:
            auto = flight.set_mode(conn, 'AUTO', table=TABLE)
            retry = time.time() + 90.0
            while not auto.ok and time.time() < retry:
                time.sleep(3)
                auto = flight.set_mode(conn, 'AUTO', table=TABLE)
            notes.append('AUTO: %r' % (auto,))

            start_t = time.time()
            injected = False
            while time.time() - start_t < 180.0:
                msg = conn.recv_match(type=['STATUSTEXT', 'HEARTBEAT'], blocking=True, timeout=1)
                if msg is None:
                    continue
                now = time.time() - start_t
                if msg.get_type() == 'STATUSTEXT':
                    notes.append('t=%5.1f s vehicle: %s' % (now, msg.text))
                    if 'Engine running' in msg.text:
                        engine_running = True
                    if 'Stopped engine' in msg.text:
                        engine_stopped = True
                elif msg.get_type() == 'HEARTBEAT' and msg.get_srcComponent() == 1:
                    if not injected and engine_running and now > 5.0:
                        injected = True
                        bad = [r.name for r in params.write(conn, [params.Change('SIM_RC_FAIL', 0.0, 1.0)]) if not r.ok]
                        notes.append('t=%5.1f s fault injected SIM_RC_FAIL=1 (rejected %s)' % (now, bad))
                    if engine_stopped and now > 10.0:
                        break
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        beat['on'] = False
        subprocess.call(['pkill', '-TERM', '-x', 'arduplane'])
        try:
            proc.wait(60)
        except Exception:
            proc.kill()
    with open(os.path.join(OUT, 'plane-ice-failsafe-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    print('[plane-ice-failsafe] engine_running=%s engine_stopped=%s' % (engine_running, engine_stopped), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
