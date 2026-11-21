"""Copter circle-fence breach, flown in LOITER: FENCE_ACTION map, time from crossing to action, FENCE_MARGIN and breach recovery. Simulator only.

Source read first (ArduCopter/fence.cpp, libraries/AC_Fence/AC_Fence.cpp, AC_Avoid.cpp): AC_Fence::check() runs at 25 Hz from Copter::fence_checks_async; a circle breach
is recorded when the distance from home reaches FENCE_RADIUS; Copter::fence_check maps FENCE_ACTION (1 RTL-or-Land, 2 Always-Land, 4 Brake-or-Land) to set_mode(); that
set_mode itself calls AC_Fence::manual_recovery_start (mode.cpp), which suppresses new breaches for 10 s. With AVOID_ENABLE bit 0 (default) AC_Avoid stops a LOITER pilot
at FENCE_RADIUS - FENCE_MARGIN before any breach. AVOID_ENABLE is AP_PARAM_FLAG_ENABLE so it is set in a prep run (-w) and the SITL restarted WITHOUT -w; FENCE_* are plain
params (AC_Fence::update re-reads FENCE_ENABLE every 10 Hz) and are written at run time on the ground.

Worker 1: SITL instance -I 1 -> MAVLink TCP 5770 (base_port 5760 + 10*I), RC UDP 5511 (5501 + 10*I) (libraries/AP_HAL_SITL/SITL_cmdline.cpp). Never kills by name.

    python3 sitl-copter-fence-circle-breach.py <ardupilot tree> <out dir> <custom-gcs dir> [case label ...]
"""
import csv
import json
import math
import os
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link  # noqa: E402
from pymavlink import mavutil  # noqa: E402

INSTANCE = 1
MAV_PORT = 5760 + 10 * INSTANCE
RC_PORT = 5501 + 10 * INSTANCE
HOME = (-35.363261, 149.165230, 584.0)
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
ALT_M = 20.0
RADIUS_M = 50.0
PITCH_FWD = 1300          # pitch stick forward 40 % (copter flies north, home heading 0)
PITCH_BACK = 1700
MODE_NAMES = {0: 'STABILIZE', 2: 'ALT_HOLD', 3: 'AUTO', 4: 'GUIDED', 5: 'LOITER', 6: 'RTL', 9: 'LAND', 17: 'BRAKE', 21: 'SMART_RTL'}
# label, AVOID_ENABLE, FENCE_ACTION, FENCE_MARGIN, FENCE_OPTIONS, manual-recovery follow-up (BRAKE case)
CASES = [
    ('rtl', 0, 1, 2.0, 0, False),
    ('land', 0, 2, 2.0, 0, False),
    ('brake', 0, 4, 2.0, 0, True),
    ('rtl-margin8-notify', 0, 1, 8.0, 4, False),
    ('avoid-on-margin2', 3, 1, 2.0, 0, False),
    ('avoid-on-margin8', 3, 1, 8.0, 0, False),
]


class Rc(threading.Thread):
    """Feeds SITL's UDP RC input (struct '<16H') at 25 Hz: roll, pitch, throttle, yaw, rest 1500. FLTMODE_CH=0 so no mode switch rides on a channel."""

    def __init__(self):
        super().__init__(daemon=True)
        self.pitch, self.thr, self.run_flag = 1500, 1000, True
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def run(self):
        while self.run_flag:
            pkt = struct.pack('<16H', *([1500, self.pitch, self.thr, 1500] + [1500] * 12))
            try:
                self.sock.sendto(pkt, ('127.0.0.1', RC_PORT))
            except OSError:
                pass
            time.sleep(0.04)


def launch(work, wipe):
    args = [BIN] + (['-w'] if wipe else []) + ['--model', '+', '-I', str(INSTANCE), '-s', '1', '--home', '%s,%s,%s,0' % HOME]
    return subprocess.Popen(args, cwd=work, stdout=open(os.path.join(work, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)


def stop(proc):
    proc.terminate()
    try:
        proc.wait(60)
    except Exception:
        proc.kill()


def set_param(conn, name, value, tries=4):
    for _ in range(tries):
        conn.mav.param_set_send(conn.target_system, conn.target_component, name.encode(), float(value), mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
        end = time.time() + 2.0
        while time.time() < end:
            m = conn.recv_match(type='PARAM_VALUE', blocking=True, timeout=0.5)
            if m is not None and m.param_id.rstrip('\x00') == name:
                return abs(m.param_value - float(value)) < 1e-4
    return False


def get_param(conn, name):
    conn.mav.param_request_read_send(conn.target_system, conn.target_component, name.encode(), -1)
    end = time.time() + 3.0
    while time.time() < end:
        m = conn.recv_match(type='PARAM_VALUE', blocking=True, timeout=0.5)
        if m is not None and m.param_id.rstrip('\x00') == name:
            return m.param_value
    return None


def warm(conn, seconds):
    end = time.time() + seconds
    while time.time() < end:
        conn.recv_match(blocking=True, timeout=0.2)


def prepare_eeprom(avoid_enable):
    """AVOID_ENABLE is an enable-flag param: set under -w, restart without -w, read it back. Returns the prepared work dir (eeprom.bin inside)."""
    prep = os.path.expanduser('~/cg-swarm-1-fence-prep-avoid%d' % avoid_enable)
    shutil.rmtree(prep, ignore_errors=True)
    os.makedirs(prep)
    proc = launch(prep, True)
    try:
        conn, _ = link.connect(MAV_PORT, timeout=120.0)
        warm(conn, 15)
        ok = [set_param(conn, 'AVOID_ENABLE', avoid_enable), set_param(conn, 'FLTMODE_CH', 0)]
    finally:
        stop(proc)
    proc = launch(prep, False)
    try:
        conn, _ = link.connect(MAV_PORT, timeout=120.0)
        warm(conn, 8)
        back = (get_param(conn, 'AVOID_ENABLE'), get_param(conn, 'FLTMODE_CH'))
    finally:
        stop(proc)
    return prep, ok, back


class Run:
    def __init__(self, conn, rc):
        self.conn, self.rc = conn, rc
        self.t0 = time.time()
        self.notes, self.track = [], []
        self.pos = None          # (n, e, alt)
        self.mode = None
        self.armed = None
        self.fstat = None
        self.max_dist = 0.0

    def t(self):
        return time.time() - self.t0

    def note(self, s):
        self.notes.append('t=%6.2f %s' % (self.t(), s))

    def dist(self):
        return None if self.pos is None else math.hypot(self.pos[0], self.pos[1])

    def pump(self, secs, until=None):
        end = time.time() + secs
        while time.time() < end:
            m = self.conn.recv_match(type=['LOCAL_POSITION_NED', 'STATUSTEXT', 'HEARTBEAT', 'FENCE_STATUS'], blocking=True, timeout=0.1)
            if m is None:
                continue
            k = m.get_type()
            if k == 'LOCAL_POSITION_NED':
                self.pos = (m.x, m.y, -m.z)
                d = self.dist()
                self.max_dist = max(self.max_dist, d)
                self.track.append([round(self.t(), 2), round(m.x, 1), round(m.y, 1), round(-m.z, 1), round(d, 1), MODE_NAMES.get(self.mode, self.mode)])
            elif k == 'STATUSTEXT':
                self.note('vehicle: %s (dist=%s)' % (m.text, None if self.dist() is None else round(self.dist(), 1)))
            elif k == 'FENCE_STATUS':
                cur = (m.breach_status, m.breach_count, m.breach_type)
                if cur != self.fstat:
                    self.note('FENCE_STATUS breach_status=%d count=%d type=%d dist=%s' % (cur + (None if self.dist() is None else round(self.dist(), 1),)))
                    self.fstat = cur
            elif k == 'HEARTBEAT' and m.get_srcComponent() == 1 and m.type not in (6, 27):
                armed = flight.is_armed(m)
                if m.custom_mode != self.mode or armed != self.armed:
                    self.note('HEARTBEAT mode=%s armed=%s dist=%s alt=%s' % (MODE_NAMES.get(m.custom_mode, m.custom_mode), armed,
                              None if self.dist() is None else round(self.dist(), 1), None if self.pos is None else round(self.pos[2], 1)))
                    self.mode, self.armed = m.custom_mode, armed
            if until is not None and until():
                return True
        return False


def run_case(label, avoid, action, margin, options, recover_back, preps):
    work = os.path.expanduser('~/cg-swarm-1-fence-' + label)
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(preps[avoid], work)
    res = {'label': label, 'AVOID_ENABLE': avoid, 'FENCE_ACTION': action, 'FENCE_MARGIN': margin, 'FENCE_OPTIONS': options, 'FENCE_RADIUS': RADIUS_M}
    rc = Rc()
    rc.start()
    proc = launch(work, False)
    run = None
    try:
        conn, _ = link.connect(MAV_PORT, timeout=120.0)
        run = Run(conn, rc)
        warm(conn, 20)
        for msg_id, us in ((32, 50000), (162, 200000), (0, 200000)):
            conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, msg_id, us, 0, 0, 0, 0, 0)
        run.note('case %s: AVOID_ENABLE=%d FENCE_ACTION=%d FENCE_MARGIN=%s FENCE_OPTIONS=%d FENCE_RADIUS=%s' % (label, avoid, action, margin, options, RADIUS_M))
        run.note('prepared params read back: AVOID_ENABLE=%s FLTMODE_CH=%s' % (get_param(conn, 'AVOID_ENABLE'), get_param(conn, 'FLTMODE_CH')))
        # FENCE_TYPE=2 (circle only) isolates the circle: the default 7 would add the 100 m max-alt and the polygon fence. FENCE_ENABLE last, no restart.
        ok = [set_param(conn, n, v) for n, v in (('FENCE_TYPE', 2), ('FENCE_RADIUS', RADIUS_M), ('FENCE_ACTION', action), ('FENCE_MARGIN', margin),
                                                 ('FENCE_OPTIONS', options), ('FENCE_ENABLE', 1))]
        run.note('fence params accepted: %s; readback FENCE_ENABLE=%s FENCE_TYPE=%s' % (ok, get_param(conn, 'FENCE_ENABLE'), get_param(conn, 'FENCE_TYPE')))
        run.pump(3)
        r = flight.set_mode(conn, 'GUIDED', table='copter')
        run.note('GUIDED: %s' % r.detail)
        armed = flight.arm(conn, timeout=120.0)
        run.note('arm: %s %s' % (armed.detail, list(armed.texts)[-3:] if not armed.ok else ''))
        res['armed'] = armed.ok
        if not armed.ok:
            return res, run
        conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, ALT_M)
        run.pump(25, until=lambda: run.pos is not None and run.pos[2] > ALT_M - 1.0)
        run.pump(4)
        run.note('takeoff done alt=%s' % (None if run.pos is None else round(run.pos[2], 1)))
        rc.thr = 1500
        r = flight.set_mode(conn, 'LOITER', table='copter')
        run.note('LOITER: %s' % r.detail)
        run.pump(4)
        # fly north under pilot control
        run.note('pitch stick forward (PWM %d)' % PITCH_FWD)
        t_stick = run.t()
        rc.pitch = PITCH_FWD
        first = {}

        def seen():
            d = run.dist()
            if d is not None and d >= RADIUS_M - margin and 'margin_cross' not in first:
                first['margin_cross'] = run.t()
                first['margin_cross_dist'] = d
            if d is not None and d >= RADIUS_M and 'cross' not in first:
                first['cross'] = run.t()
                first['cross_dist'] = d
            return run.mode != 5 and 'cross' in first

        changed = run.pump(60 if avoid == 0 else 45, until=seen)
        if avoid == 0:
            res['t_stick'] = round(t_stick, 2)
            res['t_cross'] = None if 'cross' not in first else round(first['cross'], 2)
            res['mode_changed'] = bool(changed)
            res['mode_after_breach'] = MODE_NAMES.get(run.mode, run.mode)
            res['max_dist_when_mode_changed'] = round(run.max_dist, 1)
            if changed:
                run.note('mode left LOITER; releasing pitch stick')
            rc.pitch = 1500
        else:
            run.note('avoid-on: holding pitch forward 45 s total, max dist from home so far %.1f m' % run.max_dist)
            res['max_dist_stick_held'] = round(run.max_dist, 2)
            res['mode_end_of_hold'] = MODE_NAMES.get(run.mode, run.mode)
            rc.pitch = 1500
        res['first'] = {k: round(v, 2) for k, v in first.items()}
        # watch what happens next
        if recover_back and changed:
            run.pump(12)
            res['mode_12s_after_action'] = MODE_NAMES.get(run.mode, run.mode)
            res['fence_status_12s_after'] = run.fstat
            run.note('manual recovery: LOITER + pitch back (PWM %d)' % PITCH_BACK)
            flight.set_mode(conn, 'LOITER', table='copter')
            rc.pitch = PITCH_BACK
            run.pump(40, until=lambda: run.dist() is not None and run.dist() < RADIUS_M - 8)
            rc.pitch = 1500
            run.pump(4)
            res['recovered_dist'] = None if run.dist() is None else round(run.dist(), 1)
            run.note('stick centred, watching 25 s in LOITER inside fence')
            run.pump(25)
            res['mode_after_recovery'] = MODE_NAMES.get(run.mode, run.mode)
            flight.set_mode(conn, 'LAND', table='copter')
            run.pump(40, until=lambda: run.armed is False)
        else:
            run.pump(100 if avoid == 0 else 5, until=lambda: run.armed is False)
            if run.armed:
                run.note('still armed, switching to LAND to finish')
                flight.set_mode(conn, 'LAND', table='copter')
                run.pump(60, until=lambda: run.armed is False)
        res['final_mode'] = MODE_NAMES.get(run.mode, run.mode)
        res['final_armed'] = run.armed
        res['max_dist_overall'] = round(run.max_dist, 1)
    except Exception as e:  # keep the evidence even on harness errors
        if run is not None:
            run.note('EXCEPTION %r' % (e,))
        res['exception'] = repr(e)
    finally:
        rc.run_flag = False
        stop(proc)
    return res, run


def main():
    os.makedirs(OUT, exist_ok=True)
    only = sys.argv[4:]
    todo = [c for c in CASES if not only or c[0] in only]
    preps = {}
    for avoid in sorted({c[1] for c in todo}):
        prep, ok, back = prepare_eeprom(avoid)
        preps[avoid] = prep
        print('[fence] prep avoid=%d accepted=%s readback(AVOID_ENABLE,FLTMODE_CH)=%s' % (avoid, ok, back), flush=True)
        with open(os.path.join(OUT, 'prep-avoid%d.txt' % avoid), 'w') as f:
            f.write('AVOID_ENABLE=%d set under -w accepted=%s; restart without -w; readback (AVOID_ENABLE, FLTMODE_CH)=%s\n' % (avoid, ok, back))
    results = []
    for label, avoid, action, margin, options, back in todo:
        res, run = run_case(label, avoid, action, margin, options, back, preps)
        with open(os.path.join(OUT, label + '-notes.txt'), 'w') as f:
            f.write('\n'.join(run.notes if run else []) + '\n')
        with open(os.path.join(OUT, label + '-track.csv'), 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['seconds', 'north_m', 'east_m', 'alt_m', 'dist_from_home_m', 'mode'])
            w.writerows(run.track if run else [])
        results.append(res)
        print('[fence] %s: %s' % (label, json.dumps(res)), flush=True)
    path = os.path.join(OUT, 'fence-circle-result%s.json' % ('-' + '-'.join(only) if only else ''))
    with open(path, 'w') as f:
        json.dump(results, f, indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
