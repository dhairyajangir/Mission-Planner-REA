"""Which functions of a library run in a simulated flight, shown by a debugger: the simulator binary is started under gdb with a one-shot breakpoint on each function; gdb prints
HIT <function> and the top of the call stack the first time each is reached, then lets the simulator carry on. Simulator only (WSL, gdb, the custom-gcs library).

    python3 sitl-gdb-hits.py <ardupilot tree> <out dir> <custom-gcs dir> [part ...]       parts: plane, copter, heli

plane   fixed-wing flight (takeoff, three waypoints, automatic landing) with breakpoints in APM_Control (roll, pitch, yaw, steering controllers), AP_TECS, AP_L1_Control, AP_Landing,
        AP_InertialNav, AP_ICEngine and AP_Quicktune.
copter  the standard Copter mission with breakpoints in AP_GroundEffect and AP_LandingGear.
heli    arducopter-heli, STABILIZE then ACRO requested, with a breakpoint in AC_InputManager_Heli (the helicopter's collective and stabilize-collective input handling).
Breakpoints that were never reached are listed too, with the run that shows it.
"""
import math
import os
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
PARTS = sys.argv[4:] or ['plane', 'copter', 'heli']
sys.path.insert(0, GCS)
from customgcs import flight, link, mission  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(35.363261))
WORK = os.path.expanduser('~/cg-gdb')

PLANE_FUNCTIONS = ['AP_RollController::run_axis_rate_control', 'AP_PitchController::run_axis_rate_control', 'AP_YawController::get_rate_out', 'AP_SteerController::get_steering_out_rate',
                   'AP_TECS::update_pitch_throttle', 'AP_L1_Control::update_waypoint', 'AP_Landing::verify_land', 'AP_InertialNav::update', 'AP_ICEngine::update', 'AP_Quicktune::update']
COPTER_FUNCTIONS = ['AP_GroundEffect::update', 'AP_LandingGear::update']
HELI_FUNCTIONS = ['AC_InputManager_Heli::get_pilot_desired_collective']


def gdb_script(functions):
    lines = ['set pagination off', 'set confirm off', 'handle SIGALRM SIGUSR1 SIGUSR2 SIGPIPE SIGURG nostop noprint pass']
    for fn in functions:
        lines += ['tbreak %s' % fn, 'commands', 'silent', 'printf "HIT %s\\n"' % fn, 'bt 5', 'continue', 'end']
    lines += ['run']
    path = os.path.join(WORK, 'gdb-commands.txt')
    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    return path


def start(binary, model, functions, log_name):
    os.makedirs(WORK, exist_ok=True)
    log = open(os.path.join(OUT, log_name), 'w')
    sim = [os.path.join(TREE, 'build/sitl/bin/' + binary), '-w', '--model', model, '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME]
    return subprocess.Popen(['gdb', '-q', '-batch', '-x', gdb_script(functions), '--args'] + sim, cwd=WORK, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)


def stop(proc):
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
    try:
        proc.wait(15)
    except Exception:
        proc.kill()


def at(north, east):
    return HOME[0] + north / M_LAT, HOME[1] + east / M_LON


def item(seq, command, point=(0.0, 0.0), alt=0.0, p1=0.0):
    return mission.Item(seq, 3, command, 1 if seq == 1 else 0, 1, p1, 0, 0, 0, point[0], point[1], alt)


def home_item():
    return mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2])


def fly(conn, table, items, limit):
    notes = ['upload ack %s' % mission.upload(conn, items)]
    flight.set_mode(conn, 'STABILIZE' if table == 'copter' else 'MANUAL', table=table)
    armed = flight.arm(conn, timeout=150.0)
    notes.append('arm: %s' % armed.detail)
    if not armed.ok:
        return notes
    auto = flight.set_mode(conn, 'AUTO', table=table)
    give_up = time.time() + 90.0
    while not auto.ok and time.time() < give_up:
        time.sleep(3)
        auto = flight.set_mode(conn, 'AUTO', table=table)
    notes.append('AUTO: %s' % auto.detail)
    if not auto.ok:
        return notes
    if table == 'copter':
        notes.append('start: %s' % flight.start_mission(conn).detail)
    begin, last = time.time(), None
    while time.time() - begin < limit:
        msg = conn.recv_match(type=['HEARTBEAT'], blocking=True, timeout=1)
        if msg is not None and msg.get_srcComponent() == 1 and msg.type not in (6, 27):
            if last is not None and flight.is_armed(last) and not flight.is_armed(msg):
                notes.append('disarmed by itself after %.0f s' % (time.time() - begin))
                break
            last = msg
    return notes


def summary(name, functions, notes):
    text = open(os.path.join(OUT, name + '-gdb.txt'), errors='replace').read()
    hit = [fn for fn in functions if ('HIT %s' % fn) in text]
    missed = [fn for fn in functions if fn not in hit]
    with open(os.path.join(OUT, name + '-summary.txt'), 'w') as f:
        f.write('flight notes:\n  ' + '\n  '.join(notes) + '\n')
        f.write('functions hit (%d): %s\n' % (len(hit), ', '.join(hit)))
        f.write('functions never reached (%d): %s\n' % (len(missed), ', '.join(missed)))
    print('[%s] hit %d of %d: %s | not reached: %s' % (name, len(hit), len(functions), hit, missed), flush=True)


def run_part(name, binary, model, functions, body):
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    proc = start(binary, model, functions, name + '-gdb.txt')
    notes = []
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        time.sleep(45)
        notes = body(conn)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        stop(proc)
    summary(name, functions, notes)


def plane_body(conn):
    a, b, c = at(300, 0), at(300, 300), at(0, 300)
    items = [home_item(), item(1, 22, alt=60.0, p1=15.0), item(2, 16, a, 60.0), item(3, 16, b, 60.0), item(4, 16, c, 40.0), item(5, 21, (HOME[0], HOME[1]), 0.0)]
    return fly(conn, 'plane', items, 240.0)


def copter_body(conn):
    items = [home_item(), item(1, 22, alt=15.0), item(2, 16, at(78, 0), 15.0), item(3, 16, at(78, 82), 15.0), item(4, 20)]
    return fly(conn, 'copter', items, 240.0)


def heli_body(conn):
    notes = []
    for mode in ('STABILIZE', 'ACRO', 'STABILIZE'):
        r = flight.set_mode(conn, mode)
        notes.append('%s: %s' % (mode, r.detail))
        time.sleep(4)
    return notes


def main():
    os.makedirs(OUT, exist_ok=True)
    if 'plane' in PARTS:
        run_part('plane', 'arduplane', 'plane', PLANE_FUNCTIONS, plane_body)
    if 'copter' in PARTS:
        run_part('copter', 'arducopter', '+', COPTER_FUNCTIONS, copter_body)
    if 'heli' in PARTS:
        run_part('heli', 'arducopter-heli', 'heli', HELI_FUNCTIONS, heli_body)
    return 0


if __name__ == '__main__':
    sys.exit(main())
