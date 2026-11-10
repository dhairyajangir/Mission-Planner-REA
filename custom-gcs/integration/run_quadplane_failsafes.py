"""QuadPlane failsafes, not covered by run_plane.py's failsafe scenarios (which fly a plain Plane). Disposable ArduPlane SITL, model `quadplane`. Simulator only.

    python3 run_quadplane_failsafes.py <ardupilot tree> <out dir> [scenario ...]
    scenarios: battery-low-vtol, battery-low-cruise, gps-loss-vtol, gps-loss-cruise, gcs-link-loss-transition, rc-loss-landing   (default: all)

Mission: VTOL takeoff to 30 m, a waypoint 250 m north at 60 m (the forward-flight transition happens on the way there), a second waypoint 250 m east, a VTOL landing at home
(the same mission sitl-plane-gaps.py's quadplane() flies, which is known to complete: transition, two waypoints, VTOL approach and landing).
Each scenario injects one fault at a named flight phase and watches the mode and the vehicle's own texts for 90 s:
  vtol       5 s after the VTOL takeoff begins (the vehicle is still a multicopter, before the transition)
  transition 16 s after AUTO starts (around when the transition to forward flight begins, see Plane-Frame-Types-Trace.md / sitl-plane-gaps.py: "Transition started" at 13.4 s)
  cruise     30 s after AUTO starts (level forward flight, after the transition)
  landing    sent once the vehicle's own "VTOL approach" text is seen (falls back to 140 s after AUTO if that text never appears)
Checks only that a mode change happened and is recorded, and that the vehicle did not report a simulator ground-contact impact (a crash) before reaching the expected mode; it does
not judge whether QRTL/QLAND behaved well. One run per scenario.
"""
import csv
import math
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from customgcs import flight, link, mission, params  # noqa: E402

TREE, OUT = sys.argv[1], sys.argv[2]
SCENARIOS_WANTED = sys.argv[3:] or None
HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(35.363261))

# (phase, pre-set parameters, fault parameters, expected mode)
SCENARIOS = {
    'battery-low-vtol': ('vtol', {'BATT_FS_LOW_ACT': 1, 'BATT_LOW_VOLT': 11.0, 'BATT_LOW_TIMER': 1}, {'SIM_BATT_VOLTAGE': 10.5}, 'QLAND'),
    'battery-low-cruise': ('cruise', {'BATT_FS_LOW_ACT': 1, 'BATT_LOW_VOLT': 11.0, 'BATT_LOW_TIMER': 1}, {'SIM_BATT_VOLTAGE': 10.5}, 'RTL'),
    # quadplane.parm never sets BATT_MONITOR (plane.parm sets it to 4); the compiled default is Type::NONE (AP_BattMonitor_Params.cpp), so nothing reads SIM_BATT_VOLTAGE at all.
    # This repeats battery-low-vtol with BATT_MONITOR set, to confirm that is the actual cause.
    'battery-low-vtol-monitor-set': ('vtol', {'BATT_MONITOR': 4, 'BATT_FS_LOW_ACT': 1, 'BATT_LOW_VOLT': 11.0, 'BATT_LOW_TIMER': 1}, {'SIM_BATT_VOLTAGE': 10.5}, 'QLAND'),
    'gps-loss-vtol': ('vtol', {'FS_EKF_ACTION': 1}, {'SIM_GPS1_ENABLE': 0}, 'observe'),
    'gps-loss-cruise': ('cruise', {'FS_EKF_ACTION': 1}, {'SIM_GPS1_ENABLE': 0}, 'observe'),
    'gcs-link-loss-transition': ('transition', {'FS_GCS_ENABL': 1, 'FS_LONG_ACTN': 1, 'FS_LONG_TIMEOUT': 5}, None, 'RTL'),
    'rc-loss-landing': ('landing', {'FS_LONG_ACTN': 1, 'FS_LONG_TIMEOUT': 5}, {'SIM_RC_FAIL': 1}, 'RTL'),
}


def at(north, east):
    return HOME[0] + north / M_LAT, HOME[1] + east / M_LON


def quadplane_route():
    a, b = at(250, 0), at(250, 250)
    return [mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2]), mission.Item(1, 3, 84, 1, 1, 0, 0, 0, 0, 0.0, 0.0, 30.0),
            mission.Item(2, 3, 16, 0, 1, 0, 0, 0, 0, a[0], a[1], 60.0), mission.Item(3, 3, 16, 0, 1, 0, 0, 0, 0, b[0], b[1], 60.0),
            mission.Item(4, 3, 85, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], 0.0)]


class Run:
    def __init__(self, name):
        self.name, self.lines, self.failed, self.proc, self.conn, self.beat = name, [], [], None, None, {'on': True}

    def say(self, text=''):
        print('[%s] %s' % (self.name, text), flush=True)
        self.lines.append(text)

    def check(self, label, ok, seen=''):
        self.say('%-4s %s%s' % ('OK' if ok else 'FAIL', label, ('   [' + str(seen) + ']') if seen != '' else ''))
        if not ok:
            self.failed.append(label)
        return ok

    def start(self):
        work = os.path.expanduser('~/cg-quadplane-fs')
        subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
        time.sleep(1)
        subprocess.call(['rm', '-rf', work])
        os.makedirs(work)
        self.proc = subprocess.Popen([os.path.join(TREE, 'build/sitl/bin/arduplane'), '-w', '--model', 'quadplane', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME],
                                     cwd=work, stdout=open(os.path.join(work, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
        self.conn, _ = link.connect(5760, timeout=120.0)
        self.conn.mav.heartbeat_send(6, 8, 0, 0, 0)

        def beats():
            while self.beat['on']:
                try:
                    self.conn.mav.heartbeat_send(6, 8, 0, 0, 0)
                except Exception:
                    return
                time.sleep(1.0)
        threading.Thread(target=beats, daemon=True).start()
        time.sleep(55)

    def stop(self):
        self.beat['on'] = False
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except Exception:
                self.proc.kill()

    def finish(self, track=None):
        self.lines.append('RESULT %s' % ('passed' if not self.failed else '%d checks failed: %s' % (len(self.failed), '; '.join(self.failed))))
        with open(os.path.join(OUT, self.name + '.txt'), 'w') as f:
            f.write('\n'.join(self.lines) + '\n')
        if track:
            with open(os.path.join(OUT, self.name + '-track.csv'), 'w', newline='') as f:
                w = csv.writer(f)
                w.writerow(['seconds', 'mode', 'armed'])
                w.writerows(track)


def scenario(name, phase, pre, fault, expect):
    run = Run('quadplane-' + name)
    track = []
    try:
        run.start()
        base = link.read_params(run.conn)
        bad = [r.name for r in params.write(run.conn, [params.Change(k, base.get(k), v) for k, v in pre.items()]) if not r.ok]
        run.check('parameters set %s (rejected %s)' % (pre, bad), not bad)
        run.say('upload ack %s' % mission.upload(run.conn, quadplane_route()))
        flight.set_mode(run.conn, 'MANUAL', table='plane')
        armed = flight.arm(run.conn, timeout=150.0)
        run.check('armed', armed.ok, armed.detail)
        if not armed.ok:
            run.finish(track)
            return run
        auto = flight.set_mode(run.conn, 'AUTO', table='plane')
        give_up = time.time() + 90.0
        while not auto.ok and time.time() < give_up:
            time.sleep(3)
            auto = flight.set_mode(run.conn, 'AUTO', table='plane')
        run.check('AUTO', auto.ok, auto.detail)
        begin, last_mode, injected, crashed_before = time.time(), None, False, False
        saw_vtol_approach = False
        while time.time() - begin < 90.0:
            msg = run.conn.recv_match(type=['HEARTBEAT', 'STATUSTEXT'], blocking=True, timeout=1)
            t = time.time() - begin
            if msg is not None and msg.get_type() == 'STATUSTEXT':
                run.say('t=%5.1f vehicle: %s' % (t, msg.text))
                if 'Hit ground' in msg.text and not injected:
                    crashed_before = True
                if 'VTOL approach' in msg.text:
                    saw_vtol_approach = True
            elif msg is not None and msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                mode = flight.mode_name(msg.custom_mode, 'plane')
                armed_now = flight.is_armed(msg)
                track.append([round(t, 1), mode, armed_now])
                if mode != last_mode:
                    run.say('t=%5.1f mode %s' % (t, mode))
                    last_mode = mode
            ready = ((phase == 'vtol' and t > 5) or (phase == 'transition' and t > 16) or (phase == 'cruise' and t > 30) or (phase == 'landing' and (saw_vtol_approach or t > 140)))
            if ready and not injected:
                if fault:
                    bad = [r.name for r in params.write(run.conn, [params.Change(k, None, v) for k, v in fault.items()]) if not r.ok]
                    run.say('t=%5.1f fault injected %s (rejected %s)' % (t, fault, bad))
                else:
                    run.beat['on'] = False
                    run.say('t=%5.1f ground-station heartbeats stopped' % t)
                injected = True
        run.check('no simulator ground contact before the fault was injected', not crashed_before)
        if expect == 'observe':
            run.check('mode recorded after the fault (no configured action for this fault)', last_mode is not None, last_mode)
        else:
            run.check('ended in or passed through %s' % expect, any(m == expect for _, m, _ in track), last_mode)
    except Exception as e:
        run.say('EXCEPTION %r' % (e,))
        run.failed.append('exception')
    finally:
        run.stop()
    run.finish(track)
    return run


def main():
    os.makedirs(OUT, exist_ok=True)
    names = [n for n in SCENARIOS_WANTED if n in SCENARIOS] if SCENARIOS_WANTED else list(SCENARIOS)
    runs = [scenario(name, *SCENARIOS[name]) for name in names]
    failed = [r.name for r in runs if r.failed]
    print('RESULT %s' % ('all passed' if not failed else 'failed: %s' % failed), flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
