"""Confirms that quadplane.parm's missing BATT_MONITOR (compiled default Type::NONE, AP_BattMonitor_Params.cpp) is why the battery-low failsafe never fired in
custom-gcs/integration/run_quadplane_failsafes.py. BATT_MONITOR is an AP_PARAM_FLAG_ENABLE parameter, so it (and BATT_FS_LOW_ACT, which lives under it) needs a reboot to take effect, the
same two-stage pattern as SERVO_DSHOT_ESC, SOAR_ENABLE, AROT_ENABLE and Q_TAILSIT_ENABLE elsewhere in this repository; a first attempt that set it on a live simulator with no reboot could
not arm (kept, sitl-evidence/quadplane-battery-monitor-confirm-run1-no-reboot). Simulator only (WSL, pymavlink, the custom-gcs library).

    python3 sitl-quadplane-battery-monitor-confirm.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
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
WORK = os.path.expanduser('~/cg-battmon-confirm')
BIN = os.path.join(TREE, 'build/sitl/bin/arduplane')


def at(north, east):
    return HOME[0] + north / M_LAT, HOME[1] + east / (M_LAT * math.cos(math.radians(HOME[0])))


def start(wipe):
    return subprocess.Popen([BIN] + (['-w'] if wipe else []) + ['--model', 'quadplane', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                            stdout=open(os.path.join(WORK, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    notes = []
    proc = start(True)
    try:
        conn, _ = link.connect(5760, timeout=60.0)
        time.sleep(45)
        base = link.read_params(conn)
        want = {'BATT_MONITOR': 4.0, 'BATT_FS_LOW_ACT': 1.0, 'BATT_LOW_VOLT': 11.0, 'BATT_LOW_TIMER': 1.0}
        bad = [r.name for r in params.write(conn, [params.Change(n, base.get(n), v) for n, v in want.items()]) if not r.ok]
        notes.append('set %s (rejected %s); before %s' % (want, bad, {n: base.get(n) for n in want}))
        time.sleep(2)
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
        proc = start(False)
        conn, _ = link.connect(5760, timeout=60.0)
        time.sleep(45)
        after = link.read_params(conn)
        notes.append('after reboot: %s' % {n: after.get(n) for n in want})
        notes.append('upload ack %s' % mission.upload(conn, [mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2]), mission.Item(1, 3, 84, 1, 1, 0, 0, 0, 0, 0.0, 0.0, 30.0),
                                                              mission.Item(2, 3, 16, 0, 1, 0, 0, 0, 0, at(250, 0)[0], at(250, 0)[1], 60.0), mission.Item(3, 3, 85, 0, 1, 0, 0, 0, 0, 0.0, 0.0, 0.0)]))
        flight.set_mode(conn, 'MANUAL', table='plane')
        armed = flight.arm(conn, timeout=150.0)
        notes.append('arm: %s' % armed.detail)
        if armed.ok:
            auto = flight.set_mode(conn, 'AUTO', table='plane')
            give_up = time.time() + 90.0
            while not auto.ok and time.time() < give_up:
                time.sleep(3)
                auto = flight.set_mode(conn, 'AUTO', table='plane')
            notes.append('AUTO: %s' % auto.detail)
            injected, begin, last_mode = False, time.time(), None
            while time.time() - begin < 90.0:
                msg = conn.recv_match(type=['HEARTBEAT', 'STATUSTEXT'], blocking=True, timeout=1)
                t = time.time() - begin
                if msg is not None and msg.get_type() == 'STATUSTEXT':
                    notes.append('t=%5.1f vehicle: %s' % (t, msg.text))
                elif msg is not None and msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                    mode = flight.mode_name(msg.custom_mode, 'plane')
                    if mode != last_mode:
                        notes.append('t=%5.1f mode %s' % (t, mode))
                        last_mode = mode
                if t > 10 and not injected:
                    bad2 = [r.name for r in params.write(conn, [params.Change('SIM_BATT_VOLTAGE', None, 10.5)]) if not r.ok]
                    notes.append('t=%5.1f fault injected SIM_BATT_VOLTAGE=10.5 (rejected %s)' % (t, bad2))
                    injected = True
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
        try:
            proc.wait(15)
        except Exception:
            proc.kill()
    with open(os.path.join(OUT, 'confirm-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    print('\n'.join(notes[-10:]), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
