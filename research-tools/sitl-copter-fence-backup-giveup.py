"""Copter circle-fence follow-on behaviour flown in SITL: (A) backup-fence re-breach after manual recovery, (B) the 100 m 'give up and land' rule. Simulator only.

Source read first. (A) AC_Fence::check_fence_circle records a breach at FENCE_RADIUS and sets _circle_radius_backup_m = distance_at_breach + AC_FENCE_CIRCLE_RADIUS_BACKUP_DISTANCE (20 m
on Copter); while the circle bit stays set a second breach is only reported when the vehicle reaches that backup radius. Any successful set_mode (fence-initiated or pilot) calls
AC_Fence::manual_recovery_start (mode.cpp), and check() returns 0 for 10 s (AC_FENCE_MANUAL_RECOVERY_TIME_MIN) afterwards. Hypothesis: after a BRAKE action, switching to LOITER and flying on
outward gives NO new breach for 10 s even past the backup radius; the re-breach (count 2, action again) comes when the window ends, provided the vehicle is then beyond the backup
radius; a control that holds position outside the circle never re-breaches. (B) ArduCopter/fence.cpp fence_check: if get_breach_distance() > AC_FENCE_GIVE_UP_DISTANCE (100 m) the action
is forced to LAND whatever FENCE_ACTION says. Reaching >100 m outside normally needs the fence to be off first, so the harness flies to the spot in GUIDED with FENCE_ENABLE=0 and then sends
MAV_CMD_DO_FENCE_ENABLE (AC_Fence::enable_ is the 'enabled()' test, so this works with FENCE_ENABLE=0 in params). Hypothesis: 120 m outside + action RTL -> LAND; 70 m outside + RTL -> RTL;
120 m outside + action BRAKE -> LAND.

Worker 1: SITL instance -I 1 -> MAVLink TCP 5770, RC UDP 5511. Reuses the boilerplate (Rc, launch, stop, Run, prepare_eeprom) of sitl-copter-fence-circle-breach.py. Never kills by name.

    python3 sitl-copter-fence-backup-giveup.py <ardupilot tree> <out dir> <custom-gcs dir> [case label ...]
"""
import csv
import importlib.util
import json
import math
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location('fencebase', os.path.join(HERE, 'sitl-copter-fence-circle-breach.py'))
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)
flight, link, mavutil = base.flight, base.link, base.mavutil
OUT = sys.argv[2]

TYPE_MASK_POSITION_ONLY = 0b0000111111111000
MAV_CMD_DO_FENCE_ENABLE = 207
# label, kind, FENCE_ACTION, extra
CASES = [
    ('backup-brake-fly-on', 'backup', 4, {'stick_after': True}),
    ('backup-brake-hold', 'backup', 4, {'stick_after': False}),
    ('giveup-rtl-120out', 'giveup', 1, {'north_m': 170.0}),
    ('giveup-rtl-70out', 'giveup', 1, {'north_m': 120.0}),
    ('giveup-brake-120out', 'giveup', 4, {'north_m': 170.0}),
]


def bring_up(label, action, fence_on, preps, res, notes_extra=None):
    """Start SITL from the prepared (AVOID_ENABLE=0, FLTMODE_CH=0) eeprom, set circle-only fence params, arm and climb to 20 m in GUIDED."""
    work = os.path.expanduser('~/cg-swarm-1-fbg-' + label)
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(preps[0], work)
    rc = base.Rc()
    rc.start()
    proc = base.launch(work, False)
    conn, _ = link.connect(base.MAV_PORT, timeout=120.0)
    run = base.Run(conn, rc)
    base.warm(conn, 20)
    for msg_id, us in ((32, 50000), (162, 200000), (0, 200000)):
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, msg_id, us, 0, 0, 0, 0, 0)
    ok = [base.set_param(conn, n, v) for n, v in (('FENCE_TYPE', 2), ('FENCE_RADIUS', base.RADIUS_M), ('FENCE_ACTION', action), ('FENCE_MARGIN', 2.0),
                                                  ('FENCE_OPTIONS', 0), ('FENCE_ENABLE', 1 if fence_on else 0))]
    run.note('case %s: FENCE_ACTION=%d FENCE_RADIUS=%s FENCE_TYPE=2 FENCE_OPTIONS=0 FENCE_ENABLE=%d accepted=%s readback AVOID_ENABLE=%s FENCE_ENABLE=%s' % (
        label, action, base.RADIUS_M, 1 if fence_on else 0, ok, base.get_param(conn, 'AVOID_ENABLE'), base.get_param(conn, 'FENCE_ENABLE')))
    run.pump(3)
    run.note('GUIDED: %s' % flight.set_mode(conn, 'GUIDED', table='copter').detail)
    armed = flight.arm(conn, timeout=120.0)
    run.note('arm: %s' % armed.detail)
    res['armed'] = armed.ok
    if armed.ok:
        conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, base.ALT_M)
        run.pump(25, until=lambda: run.pos is not None and run.pos[2] > base.ALT_M - 1.0)
        run.pump(4)
        run.note('takeoff done alt=%s' % (None if run.pos is None else round(run.pos[2], 1)))
    return proc, rc, conn, run


def finish(run, conn, secs=90):
    """Let whatever mode we are in finish; if still armed after secs, LAND."""
    run.pump(secs, until=lambda: run.armed is False)
    if run.armed:
        run.note('still armed after %d s; switching to LAND to finish' % secs)
        flight.set_mode(conn, 'LAND', table='copter')
        run.pump(60, until=lambda: run.armed is False)


def case_backup(label, action, extra, preps):
    res = {'label': label, 'kind': 'backup', 'FENCE_ACTION': action, 'FENCE_RADIUS': base.RADIUS_M, 'stick_after_loiter': extra['stick_after']}
    proc, rc, conn, run = bring_up(label, action, True, preps, res)
    try:
        if not res['armed']:
            return res, run
        rc.thr = 1500
        run.note('LOITER: %s' % flight.set_mode(conn, 'LOITER', table='copter').detail)
        run.pump(4)
        run.note('pitch stick forward (PWM %d)' % base.PITCH_FWD)
        rc.pitch = base.PITCH_FWD
        run.pump(60, until=lambda: run.mode not in (5, None) and run.fstat is not None and run.fstat[1] >= 1)
        res['first_breach_mode'] = base.MODE_NAMES.get(run.mode, run.mode)
        res['first_breach_dist'] = None if run.dist() is None else round(run.dist(), 1)
        res['first_breach_t'] = round(run.t(), 2)
        rc.pitch = 1500
        run.pump(3)
        res['dist_3s_after_breach'] = round(run.dist(), 1)
        res['speed_proxy'] = 'see track'
        # the pilot switches back to LOITER while still outside the circle, then either flies on outward or holds
        t_loiter = run.t()
        r = flight.set_mode(conn, 'LOITER', table='copter')
        run.note('pilot LOITER (while outside): %s' % r.detail)
        res['t_loiter'] = round(t_loiter, 2)
        res['dist_at_loiter_request'] = round(run.dist(), 1)
        n0 = run.fstat[1]
        if extra['stick_after']:
            run.note('pitch stick forward again (PWM %d)' % base.PITCH_FWD)
            rc.pitch = base.PITCH_FWD
        run.pump(45, until=lambda: run.fstat is not None and run.fstat[1] > n0)
        res['breach_count_after'] = None if run.fstat is None else run.fstat[1]
        res['rebreach_seen'] = bool(run.fstat is not None and run.fstat[1] > n0)
        if extra['stick_after'] and res['rebreach_seen']:
            # run 1 stopped here and showed count 2 with no action text/mode change (silent, inside the 10 s window); keep flying outward to see the first ACTED-ON re-breach
            res['silent_count_increment'] = {'t': round(run.t(), 2), 'dist': round(run.dist(), 1), 'seconds_since_loiter_request': round(run.t() - t_loiter, 2)}
            run.pump(40, until=lambda: run.mode != 5)
            res['acted_rebreach'] = {'mode': base.MODE_NAMES.get(run.mode, run.mode), 't': round(run.t(), 2), 'dist': round(run.dist(), 1),
                                     'seconds_since_loiter_request': round(run.t() - t_loiter, 2), 'breach_count': run.fstat[1]}
            res['breach_count_after'] = run.fstat[1]
        res['mode_at_end_of_watch'] = base.MODE_NAMES.get(run.mode, run.mode)
        res['dist_at_end_of_watch'] = round(run.dist(), 1)
        res['t_end_of_watch'] = round(run.t(), 2)
        res['seconds_since_loiter_request'] = round(run.t() - t_loiter, 2)
        rc.pitch = 1500
        if not extra['stick_after']:
            # control: hold position outside the circle in LOITER a while longer to show the window expiring changes nothing
            run.pump(15)
            res['hold_extra_15s_breach_count'] = run.fstat[1]
            res['hold_extra_15s_mode'] = base.MODE_NAMES.get(run.mode, run.mode)
        else:
            run.pump(8)
        run.note('finishing (LAND if still armed)')
        if run.mode == 5:
            flight.set_mode(conn, 'LAND', table='copter')
        finish(run, conn)
        res['final_mode'] = base.MODE_NAMES.get(run.mode, run.mode)
        res['final_armed'] = run.armed
        res['max_dist_overall'] = round(run.max_dist, 1)
    except Exception as e:
        run.note('EXCEPTION %r' % (e,))
        res['exception'] = repr(e)
    finally:
        rc.run_flag = False
        base.stop(proc)
    return res, run


def goto_local(run, conn, north_m, timeout=100.0, tol_m=4.0):
    end = time.time() + timeout
    while time.time() < end:
        conn.mav.set_position_target_local_ned_send(0, conn.target_system, conn.target_component, mavutil.mavlink.MAV_FRAME_LOCAL_NED, TYPE_MASK_POSITION_ONLY,
                                                      north_m, 0.0, -base.ALT_M, 0, 0, 0, 0, 0, 0, 0, 0)
        run.pump(0.5)
        if run.pos is not None and math.hypot(run.pos[0] - north_m, run.pos[1]) <= tol_m:
            return True
    return False


def case_giveup(label, action, extra, preps):
    res = {'label': label, 'kind': 'giveup', 'FENCE_ACTION': action, 'FENCE_RADIUS': base.RADIUS_M, 'target_north_m': extra['north_m'],
           'expected_breach_distance_m': extra['north_m'] - base.RADIUS_M}
    proc, rc, conn, run = bring_up(label, action, False, preps, res)
    try:
        if not res['armed']:
            return res, run
        rc.thr = 1500
        reached = goto_local(run, conn, extra['north_m'])
        res['reached_target'] = reached
        run.pump(4)
        res['dist_before_enable'] = round(run.dist(), 1)
        res['mode_before_enable'] = base.MODE_NAMES.get(run.mode, run.mode)
        res['fence_status_before_enable'] = run.fstat
        run.note('sending MAV_CMD_DO_FENCE_ENABLE(1) at dist=%.1f m, mode=%s' % (run.dist(), base.MODE_NAMES.get(run.mode, run.mode)))
        t_cmd = run.t()
        conn.mav.command_long_send(conn.target_system, conn.target_component, MAV_CMD_DO_FENCE_ENABLE, 0, 1, 0, 0, 0, 0, 0, 0)
        m0 = run.mode
        run.pump(30, until=lambda: run.mode != m0)
        res['t_cmd'] = round(t_cmd, 2)
        res['mode_after_breach'] = base.MODE_NAMES.get(run.mode, run.mode)
        res['seconds_cmd_to_mode_heartbeat'] = None if run.mode == m0 else round(run.t() - t_cmd, 2)
        res['dist_at_mode_change'] = round(run.dist(), 1)
        res['fence_status_after'] = run.fstat
        run.note('after enable: mode %s' % res['mode_after_breach'])
        # FENCE_ACTION=1 RTL needs long to fly 70 m+; give the autopilot's own mode time to finish, harness only intervenes if it stalls
        finish(run, conn, secs=150)
        res['final_mode'] = base.MODE_NAMES.get(run.mode, run.mode)
        res['final_armed'] = run.armed
        res['max_dist_overall'] = round(run.max_dist, 1)
    except Exception as e:
        run.note('EXCEPTION %r' % (e,))
        res['exception'] = repr(e)
    finally:
        rc.run_flag = False
        base.stop(proc)
    return res, run


def main():
    os.makedirs(OUT, exist_ok=True)
    only = sys.argv[4:]
    todo = [c for c in CASES if not only or c[0] in only]
    prep, ok, back = base.prepare_eeprom(0)
    print('[fbg] prep accepted=%s readback(AVOID_ENABLE,FLTMODE_CH)=%s' % (ok, back), flush=True)
    with open(os.path.join(OUT, 'prep-avoid0.txt'), 'w') as f:
        f.write('AVOID_ENABLE=0 set under -w accepted=%s; restart without -w; readback (AVOID_ENABLE, FLTMODE_CH)=%s\n' % (ok, back))
    results = []
    for label, kind, action, extra in todo:
        fn = case_backup if kind == 'backup' else case_giveup
        res, run = fn(label, action, extra, {0: prep})
        with open(os.path.join(OUT, label + '-notes.txt'), 'w') as f:
            f.write('\n'.join(run.notes if run else []) + '\n')
        with open(os.path.join(OUT, label + '-track.csv'), 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['seconds', 'north_m', 'east_m', 'alt_m', 'dist_from_home_m', 'mode'])
            w.writerows(run.track if run else [])
        results.append(res)
        print('[fbg] %s: %s' % (label, json.dumps(res)), flush=True)
    path = os.path.join(OUT, 'result%s.json' % ('-' + '-'.join(only) if only else ''))
    with open(path, 'w') as f:
        json.dump(results, f, indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
