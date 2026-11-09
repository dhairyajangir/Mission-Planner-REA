"""Two open Plane items, from disposable simulators (WSL, gdb, the custom-gcs library). Simulator only.

    python3 sitl-plane-gaps.py <ardupilot tree> <out dir> <custom-gcs dir> [part ...]      parts: yaw, quadplane

yaw        the earlier flight never reached AP_YawController::get_rate_out. Source (ArduPlane/mode_acro.cpp:114, Attitude.cpp:541) calls it only when the yaw rate controller is switched on
           (YAW_RATE_ENABLE, which needs a reboot to appear) and ACRO_YAW_RATE > 0 in ACRO mode. The parameters are set on a first start, the second start (no wipe) runs under gdb with
           one-shot breakpoints on get_rate_out and get_servo_out; a plane is flown by mission to altitude, then ACRO is requested.
quadplane  arduplane --model quadplane: VTOL takeoff, two waypoints and a VTOL landing by mission under gdb, with breakpoints on the QuadPlane and SLT_Transition functions; the vehicle's
           texts and the modes it reports (heartbeat) are kept with times, to show the transition between multicopter and forward flight.
"""
import json
import math
import os
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
PARTS = sys.argv[4:] or ['yaw', 'quadplane']
sys.path.insert(0, GCS)
from customgcs import flight, link, mission, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(35.363261))
WORK = os.path.expanduser('~/cg-gaps')
BIN = os.path.join(TREE, 'build/sitl/bin/arduplane')

YAW_FUNCTIONS = ['AP_YawController::get_rate_out', 'AP_YawController::get_servo_out']
QUADPLANE_FUNCTIONS = ['QuadPlane::update', 'QuadPlane::control_auto', 'QuadPlane::motors_output', 'QuadPlane::vtol_position_controller', 'QuadPlane::run_z_controller',
                       'QuadPlane::run_xy_controller', 'QuadPlane::setup_target_position', 'QuadPlane::poscontrol_init_approach', 'QuadPlane::update_land_positioning',
                       'QuadPlane::check_land_final', 'QuadPlane::check_land_complete', 'SLT_Transition::update', 'SLT_Transition::VTOL_update', 'SLT_Transition::set_FW_roll_pitch',
                       'Tiltrotor::update']


def sim_args(wipe, model):
    return (['-w'] if wipe else []), ['--model', model, '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME]


def start_plain(model, wipe):
    pre, post = sim_args(wipe, model)
    return subprocess.Popen([BIN] + pre + post, cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)


def start_gdb(model, wipe, functions, log_name):
    lines = ['set pagination off', 'set confirm off', 'handle SIGALRM SIGUSR1 SIGUSR2 SIGPIPE SIGURG nostop noprint pass']
    for fn in functions:
        lines += ['tbreak %s' % fn, 'commands', 'silent', 'printf "HIT %s\\n"' % fn, 'bt 6', 'continue', 'end']
    lines += ['run']
    script = os.path.join(WORK, 'gdb-commands.txt')
    with open(script, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    pre, post = sim_args(wipe, model)
    return subprocess.Popen(['gdb', '-q', '-batch', '-x', script, '--args', BIN] + pre + post, cwd=WORK, stdout=open(os.path.join(OUT, log_name), 'w'), stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL)


def stop_plain(proc):
    proc.terminate()
    try:
        proc.wait(10)
    except Exception:
        proc.kill()


def stop_gdb(proc):
    subprocess.call(['pkill', '-TERM', '-x', 'arduplane'])           # exact name: -f would also match the gdb command line
    try:
        proc.wait(120)
    except Exception:
        proc.kill()


def fresh():
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)


def at(north, east):
    return HOME[0] + north / M_LAT, HOME[1] + east / M_LON


def item(seq, command, point=(0.0, 0.0), alt=0.0, p1=0.0):
    return mission.Item(seq, 3, command, 1 if seq == 1 else 0, 1, p1, 0, 0, 0, point[0], point[1], alt)


def home_item():
    return mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2])


def follow(conn, notes, seconds, until=None, on_tick=None):
    """Record vehicle texts and mode changes (plane table) with times until `seconds` pass, the vehicle disarms after having been armed, or on_tick returns True."""
    begin, last, last_mode, was_armed = time.time(), None, None, False
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
            armed = flight.is_armed(msg)
            mode = flight.mode_name(msg.custom_mode, 'plane')
            if mode != last_mode:
                notes.append('t=%5.1f mode %s' % (t, mode))
                last_mode = mode
            if was_armed and not armed:
                notes.append('t=%5.1f disarmed' % t)
                break
            was_armed = was_armed or armed
    return notes


def arm_and_auto(conn, notes):
    flight.set_mode(conn, 'MANUAL', table='plane')
    armed = flight.arm(conn, timeout=150.0)
    notes.append('arm: %s' % armed.detail)
    if not armed.ok:
        return False
    auto = flight.set_mode(conn, 'AUTO', table='plane')
    give_up = time.time() + 90.0
    while not auto.ok and time.time() < give_up:
        time.sleep(3)
        auto = flight.set_mode(conn, 'AUTO', table='plane')
    notes.append('AUTO: %s' % auto.detail)
    return auto.ok


def summary(name, functions, notes):
    text = open(os.path.join(OUT, name + '-gdb.txt'), errors='replace').read()
    hit = [fn for fn in functions if ('HIT %s' % fn) in text]
    with open(os.path.join(OUT, name + '-summary.txt'), 'w') as f:
        f.write('flight notes:\n  ' + '\n  '.join(notes) + '\n')
        f.write('functions hit (%d): %s\n' % (len(hit), ', '.join(hit)))
        f.write('functions never reached (%d): %s\n' % (len(functions) - len(hit), ', '.join(fn for fn in functions if fn not in hit)))
    print('[%s] hit %d of %d: %s' % (name, len(hit), len(functions), hit), flush=True)


def yaw():
    fresh()
    notes, proc = [], None
    try:
        proc = start_plain('plane', True)
        conn, _ = link.connect(5760)
        time.sleep(15)
        base = link.read_params(conn)
        want = {'YAW_RATE_ENABLE': 1.0, 'ACRO_YAW_RATE': 30.0}
        bad = [r.name for r in params.write(conn, [params.Change(n, base.get(n), v) for n, v in want.items()]) if not r.ok]
        notes.append('set %s (rejected: %s; YAW_RATE_ENABLE existed before the write: %s)' % (want, bad, 'YAW_RATE_ENABLE' in base))
        time.sleep(2)
        stop_plain(proc)
        proc = start_gdb('plane', False, YAW_FUNCTIONS, 'yaw-gdb.txt')
        conn, _ = link.connect(5760, timeout=300.0)
        time.sleep(45)
        after = link.read_params(conn)
        notes.append('after restart YAW_RATE_ENABLE=%s ACRO_YAW_RATE=%s' % (after.get('YAW_RATE_ENABLE'), after.get('ACRO_YAW_RATE')))
        a, b = at(300, 0), at(300, 300)
        notes.append('upload ack %s' % mission.upload(conn, [home_item(), item(1, 22, alt=60.0, p1=15.0), item(2, 16, a, 60.0), item(3, 16, b, 60.0), item(4, 16, at(0, 300), 60.0)]))
        if arm_and_auto(conn, notes):
            state = {'acro': False, 'back': False}

            def tick(t):
                if t > 60 and not state['acro']:
                    notes.append('t=%5.1f requested ACRO: %s' % (t, flight.set_mode(conn, 'ACRO', table='plane').detail))
                    state['acro'] = True
                if t > 90 and not state['back']:
                    notes.append('t=%5.1f requested AUTO again: %s' % (t, flight.set_mode(conn, 'AUTO', table='plane').detail))
                    state['back'] = True
                return False
            follow(conn, notes, 150.0, on_tick=tick)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        if proc:
            stop_gdb(proc)
    summary('yaw', YAW_FUNCTIONS, notes)


def quadplane():
    fresh()
    notes, proc = [], None
    try:
        proc = start_gdb('quadplane', True, QUADPLANE_FUNCTIONS, 'quadplane-gdb.txt')
        conn, _ = link.connect(5760, timeout=300.0)
        time.sleep(45)
        p = link.read_params(conn)
        notes.append('Q_ENABLE=%s Q_FRAME_CLASS=%s Q_FRAME_TYPE=%s' % (p.get('Q_ENABLE'), p.get('Q_FRAME_CLASS'), p.get('Q_FRAME_TYPE')))
        a, b = at(250, 0), at(250, 250)
        items = [home_item(), item(1, 84, alt=30.0), item(2, 16, a, 60.0), item(3, 16, b, 60.0), item(4, 85, (HOME[0], HOME[1]), 0.0)]
        notes.append('upload ack %s' % mission.upload(conn, items))
        if arm_and_auto(conn, notes):
            follow(conn, notes, 420.0)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        if proc:
            stop_gdb(proc)
    with open(os.path.join(OUT, 'quadplane-notes.json'), 'w') as f:
        json.dump(notes, f, indent=1)
    summary('quadplane', QUADPLANE_FUNCTIONS, notes)


def main():
    os.makedirs(OUT, exist_ok=True)
    if 'yaw' in PARTS:
        yaw()
    if 'quadplane' in PARTS:
        quadplane()
    return 0


if __name__ == '__main__':
    sys.exit(main())
