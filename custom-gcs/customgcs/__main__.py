"""Command line: python -m customgcs info|plan|motor-test --port 5760 [--pct 10] [--arm]

Simulator use only so far (see README.md).
"""
import argparse
import sys

from . import link, motors


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='customgcs')
    ap.add_argument('command', choices=['info', 'plan', 'motor-test'])
    ap.add_argument('--port', type=int, default=5760)
    ap.add_argument('--pct', type=float, default=10.0)
    ap.add_argument('--arm', action='store_true', help='force-arm a simulator when the vehicle needs it (Sub)')
    args = ap.parse_args(argv)
    conn, params, info = link.inspect(args.port)
    print('vehicle: %s, frame class %s (%s), type %s (%s), %d parameters' % (info.kind, info.frame_class, info.class_param, info.frame_type, info.type_param, len(params)))
    if args.command == 'info':
        return 0
    try:
        steps = motors.plan(info, params, args.pct)
    except motors.Unsupported as e:
        print('no motor test plan:', e)
        return 2
    if args.command == 'plan':
        for s in steps:
            print('%-40s params=%s expect outputs=%s%s' % (s.label, s.params[:6], s.expect_outputs, ' (needs armed)' if s.needs_armed else ' (needs disarmed)'))
        return 0
    results = link.run_motor_test(conn, info, params, args.pct, arm=args.arm)
    bad = 0
    for r in results:
        print('%-40s expected=%-8s moved=%-8s %s %s' % (r.label, r.expected, r.moved, 'OK' if r.ok else 'MISMATCH', r.note))
        bad += 0 if r.ok else 1
    print('%d of %d steps matched' % (len(results) - bad, len(results)))
    return 0 if bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
