"""Two Plane modes the QuadPlane mode sweep could not enter, on a plain Plane (arduplane --model plane). Simulator only (WSL, gdb, the custom-gcs library).

    python3 sitl-plane-soar-autoland.py <ardupilot tree> <out dir> <custom-gcs dir> [part ...]       parts: soar, autoland

soar      THERMAL needs SoaringController::is_active(): SOAR_ENABLE 1 and the pilot's soaring switch (an RC aux, option 88, on channel 7 here; channel 8 is the Plane's flight-mode channel and RC8_OPTION conflicts with it: low = off, middle = manual mode changes,
          high = automatic). The parameters are set on a first start (SOAR_ENABLE is an enable flag whose sub-parameters appear after a reboot), the second start runs under gdb. A
          mission takes the plane to 60 m, channel 7 is moved to the middle, THERMAL is requested and held 20 s, then AUTO again.
autoland  AUTOLAND is refused for a QuadPlane ("autoland not available") and needs the takeoff direction to have been captured by a takeoff and the plane to be flying. A mission with
          a normal takeoff takes the plane up; AUTOLAND is requested 40 s later and followed for up to 150 s or until the plane disarms.
"""
import json
import math
import os
import subprocess
import sys
import threading
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
PARTS = sys.argv[4:] or ['soar', 'autoland']
sys.path.insert(0, GCS)
from customgcs import flight, link, mission, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(35.363261))
WORK = os.path.expanduser('~/cg-soar')
BIN = os.path.join(TREE, 'build/sitl/bin/arduplane')
SOAR_FUNCTIONS = ['ModeThermal::_enter', 'ModeThermal::update', 'ModeThermal::navigate', 'ModeThermal::update_soaring', 'SoaringController::update_active_state',
                  'SoaringController::init_cruising', 'SoaringController::update_cruising', 'SoaringController::init_thermalling', 'SoaringController::update_thermalling',
                  'SoaringController::update_vario', 'SoaringController::check_thermal_criteria']
AUTOLAND_FUNCTIONS = ['ModeAutoLand::_enter', 'ModeAutoLand::update', 'ModeAutoLand::navigate', 'ModeAutoLand::check_takeoff_direction', 'ModeAutoLand::landing_lined_up',
                      'ModeAutoLand::set_autoland_direction']


def start_plain(wipe):
    return subprocess.Popen([BIN] + (['-w'] if wipe else []) + ['--model', 'plane', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                            stdout=open(os.path.join(WORK, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)


def start_gdb(wipe, functions, log_name):
    lines = ['set pagination off', 'set confirm off', 'handle SIGALRM SIGUSR1 SIGUSR2 SIGPIPE SIGURG nostop noprint pass']
    for fn in functions:
        lines += ['tbreak %s' % fn, 'commands', 'silent', 'printf "HIT %s\\n"' % fn, 'bt 4', 'continue', 'end']
    lines += ['run']
    script = os.path.join(WORK, 'gdb-commands.txt')
    with open(script, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    return subprocess.Popen(['gdb', '-q', '-batch', '-x', script, '--args', BIN] + (['-w'] if wipe else []) + ['--model', 'plane', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME],
                            cwd=WORK, stdout=open(os.path.join(OUT, log_name), 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)


def fresh():
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)


def at(north, east):
    return HOME[0] + north / M_LAT, HOME[1] + east / M_LON


class Sticks(threading.Thread):
    """RC override at 10 Hz: roll, pitch and yaw centred, throttle as set (1000 while arming, a Plane refuses to arm with it up; 1500 afterwards), channel 7 as set (0 releases it)."""

    def __init__(self, conn):
        super().__init__(daemon=True)
        self.conn, self.ch8, self.throttle, self.running = conn, 0, 1000, True

    def run(self):
        while self.running:
            try:
                self.conn.mav.rc_channels_override_send(self.conn.target_system, self.conn.target_component, 1500, 1500, self.throttle, 1500, 0, 0, self.ch8, 0)
            except Exception:
                pass
            time.sleep(0.1)


def follow(conn, notes, seconds, on_tick=None):
    begin, last_mode, was_armed = time.time(), None, False
    while time.time() - begin < seconds:
        msg = conn.recv_match(type=['HEARTBEAT', 'STATUSTEXT'], blocking=True, timeout=1)
        t = time.time() - begin
        if on_tick and on_tick(t):
            break
        if msg is None:
            continue
        if msg.get_type() == 'STATUSTEXT':
            notes.append('t=%5.1f vehicle: %s' % (t, msg.text))
        elif msg.get_srcComponent() == 1 and msg.type not in (6, 27):
            armed, mode = flight.is_armed(msg), flight.mode_name(msg.custom_mode, 'plane')
            if mode != last_mode:
                notes.append('t=%5.1f mode %s' % (t, mode))
                last_mode = mode
            if was_armed and not armed:
                notes.append('t=%5.1f disarmed' % t)
                break
            was_armed = was_armed or armed


def take_off(conn, notes, loiter, sticks):
    items = [mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2]), mission.Item(1, 3, 22, 1, 1, 0, 0, 0, 0, 0.0, 0.0, 60.0)]
    if loiter:
        items.append(mission.Item(2, 3, 19, 0, 1, 900.0, 0, 0, 0, at(250, 0)[0], at(250, 0)[1], 60.0))
    else:
        items += [mission.Item(2, 3, 16, 0, 1, 0, 0, 0, 0, at(250, 0)[0], at(250, 0)[1], 60.0), mission.Item(3, 3, 16, 0, 1, 0, 0, 0, 0, at(250, 250)[0], at(250, 250)[1], 60.0)]
    notes.append('upload ack %s' % mission.upload(conn, items))
    flight.set_mode(conn, 'MANUAL', table='plane')
    armed = flight.arm(conn, timeout=150.0)
    notes.append('arm: %s' % armed.detail)
    if not armed.ok:                                                 # keep the vehicle's pre-arm texts, which say why
        flight._arm_command(conn, True, False)
        end = time.time() + 6.0
        while time.time() < end:
            msg = conn.recv_match(type=['STATUSTEXT'], blocking=True, timeout=1)
            if msg is not None:
                notes.append('vehicle: %s' % msg.text)
    auto = flight.set_mode(conn, 'AUTO', table='plane')
    give_up = time.time() + 90.0
    while not auto.ok and time.time() < give_up:
        time.sleep(3)
        auto = flight.set_mode(conn, 'AUTO', table='plane')
    notes.append('AUTO: %s' % auto.detail)
    sticks.throttle = 1500
    return armed.ok and auto.ok


def summary(name, functions, notes):
    text = open(os.path.join(OUT, name + '-gdb.txt'), errors='replace').read()
    hit = [fn for fn in functions if 'HIT %s' % fn in text]
    with open(os.path.join(OUT, name + '-summary.txt'), 'w') as f:
        f.write('flight notes:\n  ' + '\n  '.join(notes) + '\n')
        f.write('functions hit (%d): %s\n' % (len(hit), ', '.join(hit)))
        f.write('functions never reached (%d): %s\n' % (len(functions) - len(hit), ', '.join(fn for fn in functions if fn not in hit)))
    print('[%s] hit %d of %d; not reached %s' % (name, len(hit), len(functions), [fn for fn in functions if fn not in hit]), flush=True)


def stop_gdb(proc):
    subprocess.call(['pkill', '-TERM', '-x', 'arduplane'])
    try:
        proc.wait(120)
    except Exception:
        proc.kill()


def soar():
    fresh()
    notes, proc, sticks = [], None, None
    try:
        proc = start_plain(True)
        conn, _ = link.connect(5760)
        time.sleep(15)
        base = link.read_params(conn)
        want = {'SOAR_ENABLE': 1.0, 'RC7_OPTION': 88.0}
        bad = [r.name for r in params.write(conn, [params.Change(n, base.get(n), v) for n, v in want.items()]) if not r.ok]
        notes.append('set %s (rejected %s); before %s' % (want, bad, {n: base.get(n) for n in want}))
        time.sleep(2)
        proc.terminate()
        proc.wait(10)
        proc = start_gdb(False, SOAR_FUNCTIONS, 'soar-gdb.txt')
        conn, _ = link.connect(5760, timeout=300.0)
        time.sleep(45)
        sticks = Sticks(conn)
        sticks.start()
        if take_off(conn, notes, True, sticks):
            state = {'mid': False, 'thermal': False, 'auto': False}

            def tick(t):
                if t > 50 and not state['mid']:
                    sticks.ch8 = 1500
                    state['mid'] = True
                    notes.append('t=%5.1f channel 7 to middle' % t)
                if t > 60 and not state['thermal']:
                    r = flight.set_mode(conn, 'THERMAL', table='plane')
                    notes.append('t=%5.1f THERMAL: %s' % (t, r.detail))
                    state['thermal'] = True
                if t > 85 and not state['auto']:
                    notes.append('t=%5.1f AUTO: %s' % (t, flight.set_mode(conn, 'AUTO', table='plane').detail))
                    state['auto'] = True
                return t > 100
            follow(conn, notes, 110.0, tick)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        if sticks:
            sticks.running = False
        if proc:
            stop_gdb(proc)
    summary('soar', SOAR_FUNCTIONS, notes)


def autoland():
    fresh()
    notes, proc, sticks = [], None, None
    try:
        proc = start_gdb(True, AUTOLAND_FUNCTIONS, 'autoland-gdb.txt')
        conn, _ = link.connect(5760, timeout=300.0)
        time.sleep(45)
        sticks = Sticks(conn)
        sticks.start()
        if take_off(conn, notes, False, sticks):
            state = {'asked': False}

            def tick(t):
                if t > 40 and not state['asked']:
                    notes.append('t=%5.1f AUTOLAND: %s' % (t, flight.set_mode(conn, 'AUTOLAND', table='plane').detail))
                    state['asked'] = True
                return False
            follow(conn, notes, 190.0, tick)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        if sticks:
            sticks.running = False
        if proc:
            stop_gdb(proc)
    summary('autoland', AUTOLAND_FUNCTIONS, notes)


def main():
    os.makedirs(OUT, exist_ok=True)
    if 'soar' in PARTS:
        soar()
    if 'autoland' in PARTS:
        autoland()
    return 0


if __name__ == '__main__':
    sys.exit(main())
