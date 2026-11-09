"""Command line for the prototype ground station. Simulator use only so far (see README.md).

    python -m customgcs info|plan|motor-test               [--port 5760] [--pct 10] [--arm]
    python -m customgcs params-save|params-diff|params-restore  --file F [--dry-run] [--include-protected]
    python -m customgcs modes [--vehicle copter|rover|plane] | mode --name LOITER | arm [--force] | disarm [--force]
    python -m customgcs mission-upload|mission-download|mission-verify --file F | mission-clear | mission-start

Commands that change the vehicle (everything except info, plan, modes, params-save, params-diff, mission-download, mission-verify) refuse a host other than the local machine
unless --allow-remote is given: the prototype has only ever been run against simulators.
"""
import argparse
import sys

from . import flight, link, mission, motors, params

READ_ONLY = ('info', 'plan', 'modes', 'params-save', 'params-diff', 'mission-download', 'mission-verify')
LOOPBACK = ('127.0.0.1', 'localhost', '::1')


def _motor_commands(args, conn, info, parameters) -> int:
    try:
        steps = motors.plan(info, parameters, args.pct)
    except motors.Unsupported as e:
        print('no motor test plan:', e)
        return 2
    if args.command == 'plan':
        for s in steps:
            print('%-40s params=%s expect outputs=%s%s' % (s.label, s.params[:6], s.expect_outputs, ' (needs armed)' if s.needs_armed else ' (needs disarmed)'))
        return 0
    results = link.run_motor_test(conn, info, parameters, args.pct, arm=args.arm)
    bad = 0
    for r in results:
        print('%-40s expected=%-8s moved=%-8s %s %s' % (r.label, r.expected, r.moved, 'OK' if r.ok else 'MISMATCH', r.note))
        bad += 0 if r.ok else 1
    print('%d of %d steps matched' % (len(results) - bad, len(results)))
    return 0 if bad == 0 else 1


def _params_commands(args, conn, parameters) -> int:
    if not args.file:
        print('--file is required')
        return 2
    if args.command == 'params-save':
        with open(args.file, 'w', encoding='utf-8') as f:
            f.write(params.dumps(parameters, '%d parameters' % len(parameters)))
        print('saved %d parameters to %s' % (len(parameters), args.file))
        return 0
    with open(args.file, encoding='utf-8') as f:
        wanted = params.loads(f.read())
    if args.command == 'params-diff':
        changes = params.diff(parameters, wanted)
        for c in changes:
            print('%-28s vehicle=%-14s file=%-14s%s' % (c.name, 'missing' if c.old is None else '%.9g' % c.old, '%.9g' % c.new, '  (vehicle-maintained)' if params.volatile(c.name) else ''))
        real = [c for c in changes if not params.volatile(c.name)]
        print('%d differences, %d of them settings (%d in file, %d on vehicle)' % (len(changes), len(real), len(wanted), len(parameters)))
        return 0 if not real else 1
    hb = flight.current_heartbeat(conn)
    report = params.restore(conn, wanted, link.read_params, armed=bool(hb is not None and flight.is_armed(hb)), include_protected=args.include_protected, dry_run=args.dry_run)
    for c in report.planned:
        print('%s %-28s %s -> %.9g' % ('would set' if args.dry_run else 'set', c.name, 'missing' if c.old is None else '%.9g' % c.old, c.new))
    for r in report.results:
        if not r.ok:
            print('FAILED %-26s wanted %.9g got %s (%s)' % (r.name, r.wanted, r.got, r.note))
    if report.skipped_protected:
        print('not touched (protected): %s' % ' '.join(report.skipped_protected))
    print('%d planned (dry run, nothing written)' % len(report.planned) if args.dry_run else '%d planned, %d still different afterwards' % (len(report.planned), len(report.remaining)))
    return 0 if args.dry_run or not report.remaining else 1


def _flight_commands(args, conn, info) -> int:
    if args.command == 'arm':
        result = flight.arm(conn, force=args.force)
    elif args.command == 'disarm':
        result = flight.disarm(conn, force=args.force)
    else:
        if not args.name:
            print('--name is required')
            return 2
        result = flight.set_mode(conn, args.name, table=flight.table_for(info.kind))
    print(result.detail)
    for t in result.texts:
        print('  vehicle says:', t)
    return 0 if result.ok else 1


def _mission_commands(args, conn) -> int:
    kind = {'mission': mission.MISSION, 'fence': mission.FENCE, 'rally': mission.RALLY}[args.list]
    if args.command == 'mission-clear':
        print('mission clear ack type', mission.clear(conn, mission_type=kind))
        return 0
    if args.command == 'mission-start':
        result = flight.start_mission(conn)
        print(result.detail)
        return 0 if result.ok else 1
    if not args.file:
        print('--file is required')
        return 2
    if args.command == 'mission-download':
        items = mission.download(conn, mission_type=kind)
        with open(args.file, 'w', encoding='utf-8') as f:
            f.write(mission.dumps_wpl(items))
        print('downloaded %d items to %s' % (len(items), args.file))
        return 0
    with open(args.file, encoding='utf-8') as f:
        items = mission.loads_wpl(f.read())
    if args.command == 'mission-upload':
        ack = mission.upload(conn, items, mission_type=kind)
        print('uploaded %d items, ack type %d (%s)' % (len(items), ack, 'accepted' if ack == 0 else 'refused'))
        return 0 if ack == 0 else 1
    problems = mission.verify(items, mission.download(conn, mission_type=kind), skip_home=(kind == mission.MISSION))
    for p in problems:
        print(p)
    print('mission matches the file' if not problems else '%d differences' % len(problems))
    return 0 if not problems else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='customgcs')
    ap.add_argument('command', choices=['info', 'plan', 'motor-test', 'params-save', 'params-diff', 'params-restore', 'modes', 'mode', 'arm', 'disarm',
                                        'mission-upload', 'mission-download', 'mission-verify', 'mission-clear', 'mission-start'])
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=5760)
    ap.add_argument('--allow-remote', action='store_true', help='allow a state-changing command on a host that is not this machine (never tried; the prototype is simulator-only)')
    ap.add_argument('--pct', type=float, default=10.0)
    ap.add_argument('--arm', action='store_true', help='force-arm a simulator when the motor test needs it (Sub)')
    ap.add_argument('--force', action='store_true', help='arm/disarm without the vehicle\'s checks')
    ap.add_argument('--vehicle', choices=['copter', 'rover', 'plane'], default='copter', help='for the modes listing, which vehicle modes to show')
    ap.add_argument('--file')
    ap.add_argument('--list', choices=['mission', 'fence', 'rally'], default='mission', help='which list the mission-* commands work on: the mission, the geofence or the rally points')
    ap.add_argument('--name')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--include-protected', action='store_true')
    args = ap.parse_args(argv)
    if args.command == 'modes':
        for name, number in sorted(flight.vehicle_modes(args.vehicle).items(), key=lambda kv: kv[1]):
            print('%2d %s' % (number, name))
        return 0
    if args.command not in READ_ONLY and args.host not in LOOPBACK and not args.allow_remote:
        print('refusing %s on %s: only simulators on this machine have been tested; pass --allow-remote to override' % (args.command, args.host))
        return 3
    try:
        return _run(args)
    except (RuntimeError, ValueError, TimeoutError, KeyError) as e:      # a refusal or a bad file: say what it was, do not show a traceback
        print('error: %s' % (e.args[0] if isinstance(e, KeyError) and e.args else e))
        return 4


def _run(args) -> int:
    conn, parameters, info = link.inspect(args.port, args.host)
    print('vehicle: %s, frame class %s (%s), type %s (%s), %d parameters' % (info.kind, info.frame_class, info.class_param, info.frame_type, info.type_param, len(parameters)))
    if args.command == 'info':
        return 0
    if args.command in ('plan', 'motor-test'):
        return _motor_commands(args, conn, info, parameters)
    if args.command.startswith('params-'):
        return _params_commands(args, conn, parameters)
    if args.command.startswith('mission-'):
        return _mission_commands(args, conn)
    return _flight_commands(args, conn, info)


if __name__ == '__main__':
    sys.exit(main())
