"""Breakpoint sweep over ArduPilot libraries that the register lists as inventoried only: which of their init / update / read / loop functions run in a simulated Copter flight,
a simulated Plane flight and an idle helicopter build. Simulator only (WSL, gdb, the custom-gcs library).

    python3 sitl-gdb-library-sweep.py <ardupilot tree> <out dir> <custom-gcs dir> [vehicle ...]      vehicles: copter, plane, heli

For every class in CLASSES the binary's own symbol table (nm -C) gives the init / update / loop / read / run / setup functions that exist (`<name>-functions.txt`); each gets a breakpoint that continues silently. After the run (the simulator is stopped with
SIGTERM) `info breakpoints` prints each breakpoint's hit count. The output file lists, per class, the functions that exist in the binary and how often each was hit. A class with no
matching function in a binary is reported as absent; an existing function with zero hits means the feature was not active in that run (most are disabled by default).
"""
import math
import os
import re
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
VEHICLES = sys.argv[4:] or ['copter', 'plane', 'heli']
sys.path.insert(0, GCS)
from customgcs import flight, link, mission  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(35.363261))
WORK = os.path.expanduser('~/cg-gdbsweep')
SIM_NAME = ''
# library -> classes (the class names were taken from the library sources)
CLASSES = {
    'AP_Notify': ['AP_Notify'], 'AP_RCMapper': ['RCMapper'], 'AP_SerialManager': ['AP_SerialManager'], 'AP_BoardConfig': ['AP_BoardConfig'], 'AP_RSSI': ['AP_RSSI'],
    'AP_Servo_Telem': ['AP_Servo_Telem'], 'AP_TempCalibration': ['AP_TempCalibration'], 'AP_TemperatureSensor': ['AP_TemperatureSensor'], 'AP_OSD': ['AP_OSD'],
    'AP_LandingGear': ['AP_LandingGear'], 'AP_InternalError': ['AP_InternalError'], 'StorageManager': ['StorageManager'], 'AP_ExternalControl': ['AP_ExternalControl'],
    'AP_CustomControl': ['AP_CustomControl'], 'AP_CANManager': ['AP_CANManager'], 'AP_EFI': ['AP_EFI'], 'AP_WindVane': ['AP_WindVane'], 'AP_Frsky_Telem': ['AP_Frsky_Telem'],
    'AP_RCTelemetry': ['AP_RCTelemetry'], 'AP_VideoTX': ['AP_VideoTX'], 'AP_OpenDroneID': ['AP_OpenDroneID'], 'AP_IRLock': ['AP_IRLock'], 'AP_SerialLED': ['AP_SerialLED'],
    'AP_SBusOut': ['AP_SBusOut'], 'AP_CustomRotations': ['AP_CustomRotations'], 'AP_Hott_Telem': ['AP_Hott_Telem'], 'AP_LTM_Telem': ['AP_LTM_Telem'], 'AP_Devo_Telem': ['AP_Devo_Telem'],
    'AP_Torqeedo': ['AP_Torqeedo'], 'AP_BLHeli': ['AP_BLHeli'], 'AP_KDECAN': ['AP_KDECAN'], 'AP_PiccoloCAN': ['AP_PiccoloCAN'], 'AP_RobotisServo': ['AP_RobotisServo'],
    'AP_ADC': ['AP_ADC'], 'AP_DAC': ['AP_DAC'], 'AP_DDS': ['AP_DDS_Client'], 'AP_FlashIface': ['AP_FlashIface'], 'AP_IOMCU': ['AP_IOMCU'], 'AP_Menu': ['AP_Menu'], 'AP_Module': ['AP_Module'],
    'AP_Radio': ['AP_Radio'], 'AP_CheckFirmware': ['AP_CheckFirmware'],
}
PATTERN = '(init|update|loop|read|run|setup)'
# SWEEP_CLASSES="RCMapper,AP_JSON,..." replaces CLASSES (one library per class) and, with it, every function of those classes is instrumented instead of only init/update/loop/read/run/setup
if os.environ.get('SWEEP_CLASSES'):
    CLASSES = {c: [c] for c in os.environ['SWEEP_CLASSES'].split(',')}
    PATTERN = r'\w+'


def home_item():
    return mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2])


def at(north, east):
    return HOME[0] + north / M_LAT, HOME[1] + east / M_LON


def item(seq, command, point=(0.0, 0.0), alt=0.0, p1=0.0):
    return mission.Item(seq, 3, command, 1 if seq == 1 else 0, 1, p1, 0, 0, 0, point[0], point[1], alt)


def symbols_for(binary):
    """{'Class::function'} present in the binary for every class in CLASSES, from its own symbol table (nm -C), limited to init/update/loop/read/run/setup functions."""
    names = '|'.join(re.escape(c) for classes in CLASSES.values() for c in classes)
    pattern = re.compile(r'^[0-9a-f]+ [Tt] ((?:%s)::%s\w*)\(' % (names, '(?:init|update|loop|read|run|setup)' if PATTERN != r'\w+' else ''))
    found = set()
    out = subprocess.run(['nm', '-C', os.path.join(TREE, 'build/sitl/bin/' + binary)], capture_output=True, text=True).stdout
    for line in out.splitlines():
        m = pattern.match(line)
        if m:
            found.add(m.group(1))
    return sorted(found)


def gdb_commands(path, functions):
    lines = ['set pagination off', 'set confirm off', 'handle SIGALRM SIGUSR1 SIGUSR2 SIGPIPE SIGURG nostop noprint pass']
    for fn in functions:
        lines += ['break %s' % fn, 'commands', 'silent', 'continue', 'end']
    lines += ['run', 'info breakpoints']
    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')


def start(binary, model, name):
    global SIM_NAME
    SIM_NAME = binary
    os.makedirs(WORK, exist_ok=True)
    script = os.path.join(WORK, 'gdb-commands.txt')
    functions = symbols_for(binary)
    with open(os.path.join(OUT, name + '-functions.txt'), 'w') as f:
        f.write('\n'.join(functions) + '\n')
    gdb_commands(script, functions)
    log = open(os.path.join(OUT, name + '-gdb.txt'), 'w')
    sim = [os.path.join(TREE, 'build/sitl/bin/' + binary), '-w', '--model', model, '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME]
    return subprocess.Popen(['gdb', '-q', '-batch', '-x', script, '--args'] + sim, cwd=WORK, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)


def stop(proc):
    subprocess.call(['pkill', '-TERM', '-x', SIM_NAME])       # exact process name: `-f` would also match the gdb command line and kill gdb before it prints the table
    try:
        proc.wait(180)
    except Exception:
        proc.kill()


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


def parse_hits(text):
    """[(function, hits)] from the `info breakpoints` table at the end of the gdb output."""
    table = text[text.rfind('Num     Type'):] if 'Num     Type' in text else ''
    out, current = [], None
    for line in table.splitlines():
        m = re.match(r'\s*\d+\s+breakpoint\s+keep\s+\w\s+0x[0-9a-f]+\s+(?:in\s+(.+?)\s+at\s|<(.+)>\s*$)', line)   # two table layouts: `in fn at file:line` and `<fn(args)>`
        if m:
            current = [re.sub(r'\(.*$', '', m.group(1) or m.group(2)), 0]
            out.append(current)
            continue
        h = re.match(r'\s*breakpoint already hit (\d+) time', line)
        if h and current is not None:
            current[1] = int(h.group(1))
    return [(f, n) for f, n in out]


def run_vehicle(name, binary, model, body):
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    proc = start(binary, model, name)
    notes = []
    try:
        conn, _ = link.connect(5760, timeout=600.0)             # many breakpoints make the start slow
        time.sleep(45)
        notes = body(conn)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        stop(proc)
    write_results(name, notes)


def write_results(name, notes):
    text = open(os.path.join(OUT, name + '-gdb.txt'), errors='replace').read()
    hits = parse_hits(text)
    with open(os.path.join(OUT, name + '-hits.csv'), 'w') as f:
        f.write('library,function,hits\n')
        for fn, n in hits:
            owner = next((lib for lib, classes in CLASSES.items() if any(fn.startswith(c + '::') for c in classes)), '')
            f.write('%s,"%s",%d\n' % (owner, fn, n))
    with open(os.path.join(OUT, name + '-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n%d breakpoints set, %d functions hit at least once\n' % (len(hits), sum(1 for _, n in hits if n)))
    print('[%s] %d breakpoints, %d hit; %s' % (name, len(hits), sum(1 for _, n in hits if n), notes[-1] if notes else ''), flush=True)


def copter_body(conn):
    items = [home_item(), item(1, 22, alt=15.0), item(2, 16, at(78, 0), 15.0), item(3, 16, at(78, 82), 15.0), item(4, 20)]
    return fly(conn, 'copter', items, 240.0)


def plane_body(conn):
    a, b, c = at(300, 0), at(300, 300), at(0, 300)
    items = [home_item(), item(1, 22, alt=60.0, p1=15.0), item(2, 16, a, 60.0), item(3, 16, b, 60.0), item(4, 16, c, 40.0), item(5, 21, (HOME[0], HOME[1]), 0.0)]
    return fly(conn, 'plane', items, 240.0)


def heli_body(conn):
    notes = []
    for mode in ('STABILIZE', 'ACRO', 'STABILIZE'):
        notes.append('%s: %s' % (mode, flight.set_mode(conn, mode).detail))
        time.sleep(5)
    time.sleep(30)
    return notes


def reparse():
    """Rebuild <name>-hits.csv and <name>-notes.txt from the existing <name>-gdb.txt (keeps the flight notes already in <name>-notes.txt)."""
    for name in VEHICLES:
        old = open(os.path.join(OUT, name + '-notes.txt')).read().splitlines()
        write_results(name, [line for line in old if 'breakpoints set' not in line])


def main():
    os.makedirs(OUT, exist_ok=True)
    if os.environ.get('REPARSE'):
        reparse()
        return 0
    if 'copter' in VEHICLES:
        run_vehicle('copter', 'arducopter', '+', copter_body)
    if 'plane' in VEHICLES:
        run_vehicle('plane', 'arduplane', 'plane', plane_body)
    if 'heli' in VEHICLES:
        run_vehicle('heli', 'arducopter-heli', 'heli', heli_body)
    return 0


if __name__ == '__main__':
    sys.exit(main())
