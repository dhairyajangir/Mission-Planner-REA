"""Parameters, arm/modes and missions of the prototype against one disposable Copter simulator (WSL, ArduPilot SITL, pymavlink). Simulator only.

    python3 run_functions.py <ardupilot tree> <out dir>

Writes <out>/functions-run.txt (every check as OK or FAIL with what was seen) plus the parameter file and WPL files it produced. Exit code 1 if any check failed.
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from customgcs import flight, link, mission, params  # noqa: E402

TREE, OUT = sys.argv[1], sys.argv[2]
HOME = (-35.363261, 149.165230, 584.0)
LINES = []
FAILED = []


def say(text=''):
    print(text, flush=True)
    LINES.append(text)


def check(label, ok, seen=''):
    say('%-4s %s%s' % ('OK' if ok else 'FAIL', label, ('   [' + str(seen) + ']') if seen != '' else ''))
    if not ok:
        FAILED.append(label)
    return ok


def section_params(conn):
    say('== parameters')
    base = link.read_params(conn)
    path = os.path.join(OUT, 'params-baseline.param')
    with open(path, 'w') as f:
        f.write(params.dumps(base, 'baseline of this run'))
    saved = params.loads(open(path).read())
    check('saved file reloads to the same %d parameters' % len(base), params.diff(base, saved) == [] and params.diff(saved, base) == [])
    wanted_changes = [params.Change('PILOT_SPD_UP', base['PILOT_SPD_UP'], 3.0), params.Change('RTL_ALT_M', base['RTL_ALT_M'], 20.0), params.Change('LAND_SPD_MS', base['LAND_SPD_MS'], 0.75)]
    results = params.write(conn, wanted_changes)
    check('three parameters written and echoed by the vehicle', all(r.ok for r in results), [(r.name, r.got) for r in results])
    changed = link.read_params(conn)
    names = [c.name for c in params.diff(base, changed) if not params.protected(c.name)]
    check('diff against the saved file lists exactly those three', sorted(names) == ['LAND_SPD_MS', 'PILOT_SPD_UP', 'RTL_ALT_M'], names)
    dry = params.restore(conn, saved, link.read_params, armed=False, dry_run=True)
    check('dry run plans the three and writes nothing', sorted(c.name for c in dry.planned) == ['LAND_SPD_MS', 'PILOT_SPD_UP', 'RTL_ALT_M'] and link.read_params(conn)['RTL_ALT_M'] == 20.0)
    tampered = dict(saved)
    tampered['SERIAL0_BAUD'] = saved['SERIAL0_BAUD'] + 1
    report = params.restore(conn, tampered, link.read_params, armed=False)
    after = link.read_params(conn)
    check('restore wrote three, skipped the protected SERIAL0_BAUD, nothing else differs', sorted(c.name for c in report.planned) == ['LAND_SPD_MS', 'PILOT_SPD_UP', 'RTL_ALT_M']
          and report.skipped_protected == ('SERIAL0_BAUD',) and report.remaining == () and after['SERIAL0_BAUD'] == saved['SERIAL0_BAUD'], (report.skipped_protected, len(report.remaining)))
    rest = [c.name for c in params.diff(after, saved) if not params.protected(c.name)]
    check('after restore the vehicle matches the saved file (protected names excluded)', rest == [], rest[:5])
    refused = params.write(conn, [params.Change('NO_SUCH_PARAMETER_X', None, 1.0)], timeout=1.0, tries=1)
    check('a parameter the vehicle does not have is reported, not silently accepted', not refused[0].ok, refused[0].note)


def sweep(conn, label):
    say('     -- every mode requested one by one, %s' % label)
    for name, number in sorted(flight.copter_modes().items(), key=lambda kv: kv[1]):
        result = flight.set_mode(conn, name)
        say('     mode %2d %-13s %s%s' % (number, name, result.detail, ('  | ' + '; '.join(result.texts[-2:])) if result.texts else ''))
        if name != 'STABILIZE' or not result.ok:
            back = flight.set_mode(conn, 'STABILIZE')
            if not back.ok:
                say('     could not return to STABILIZE: %s' % back.detail)


def section_flight(conn):
    say('== arm and modes')
    early = flight.arm(conn, timeout=6.0)
    say('     early arm attempt (about 15 s after start): %s | %s' % (early.detail, '; '.join(early.texts[-3:])))
    if early.ok:
        say('     the vehicle armed within 6 s (a refused first try, then accepted); disarming before the disarmed sweep: %s' % flight.disarm(conn).detail)
    time.sleep(45)                                          # EKF origin and GPS use came 18 to 41 s after start in earlier runs
    hb = flight.current_heartbeat(conn)
    check('vehicle is disarmed before the disarmed sweep', hb is not None and not flight.is_armed(hb))
    say('     start mode: %s' % flight.current_mode(conn))
    sweep(conn, 'disarmed')
    check('STABILIZE is accepted', flight.set_mode(conn, 'STABILIZE').ok)
    armed = flight.arm(conn, timeout=60.0)
    check('arm succeeds', armed.ok, armed.detail)
    hb = flight.current_heartbeat(conn)
    check('heartbeat reports armed', hb is not None and flight.is_armed(hb))
    try:
        params.restore(conn, {'PILOT_SPD_UP': 2.0}, link.read_params, armed=bool(hb is not None and flight.is_armed(hb)))
        check('parameter restore refuses while armed', False)
    except RuntimeError as e:
        check('parameter restore refuses while armed', True, e)
    sweep(conn, 'armed on the ground in the simulator')
    off = flight.disarm(conn)
    check('disarm succeeds', off.ok, off.detail)
    flight.set_mode(conn, 'STABILIZE')
    try:
        flight.set_mode(conn, 'SPACESHIP')
        check('unknown mode name rejected before sending', False)
    except KeyError:
        check('unknown mode name rejected before sending', True)


def wp(seq, command, x, y, z, frame=3, p1=0.0):
    return mission.Item(seq, frame, command, 1 if seq == 1 else 0, 1, p1, 0.0, 0.0, 0.0, x, y, z)


def section_mission(conn):
    say('== missions')
    items = [wp(0, 16, HOME[0], HOME[1], HOME[2], frame=0), wp(1, 22, 0.0, 0.0, 15.0), wp(2, 16, -35.36250, 149.16600, 20.0, p1=2.0), wp(3, 16, -35.36190, 149.16690, 25.5), wp(4, 20, 0.0, 0.0, 0.0)]
    ack = mission.upload(conn, items)
    check('upload of 5 items accepted (ack type 0)', ack == 0, ack)
    got = mission.download(conn)
    problems = mission.verify(items, got)
    check('download returns the same items from 1 to 4 (home replaced by the vehicle\'s)', problems == [] and len(got) == 5, problems[:3])
    path = os.path.join(OUT, 'mission-downloaded.waypoints')
    with open(path, 'w') as f:
        f.write(mission.dumps_wpl(got))
    reloaded = mission.loads_wpl(open(path).read())
    check('downloaded mission survives a WPL file round trip', mission.verify(got, reloaded) == [] and len(reloaded) == len(got))
    bad = list(items)
    bad[2] = wp(2, 16, float('nan'), 149.16600, 20.0)
    try:
        mission.upload(conn, bad)
        check('NaN latitude refused before anything is sent', False)
    except ValueError as e:
        check('NaN latitude refused before anything is sent', True, e)
    check('vehicle mission unchanged by the refused upload', mission.verify(items, mission.download(conn)) == [])
    odd = list(items[:3]) + [wp(3, 9999, -35.3619, 149.1669, 25.0)]
    ack = mission.upload(conn, odd)
    say('     unknown command 9999 -> ack type %d' % ack)
    check('vehicle answered the unknown command with a MISSION_ACK (type recorded above)', True, ack)
    ack = mission.upload(conn, items)
    check('re-upload of the good mission accepted', ack == 0, ack)
    check('clear accepted (ack type 0)', mission.clear(conn) == 0)
    left = mission.download(conn)
    say('     items left after clear: %d' % len(left))
    check('mission empty after clear except possibly home', len(left) <= 1, len(left))


def main():
    os.makedirs(OUT, exist_ok=True)
    work = os.path.expanduser('~/cg-functions')
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', work])
    os.makedirs(work)
    proc = subprocess.Popen([os.path.join(TREE, 'build/sitl/bin/arducopter'), '-w', '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME],
                            cwd=work, stdout=open(os.path.join(work, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    try:
        conn, mav_type = link.connect(5760)
        say('connected; vehicle type %d' % mav_type)
        time.sleep(10)
        for section in (section_flight, section_params, section_mission):
            try:
                section(conn)
            except Exception as e:                         # keep the failure as the record
                check('%s finished without an exception' % section.__name__, False, repr(e))
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
    say('')
    say('RESULT %s' % ('all checks passed' if not FAILED else '%d checks failed: %s' % (len(FAILED), '; '.join(FAILED))))
    with open(os.path.join(OUT, 'functions-run.txt'), 'w') as f:
        f.write('\n'.join(LINES) + '\n')
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
