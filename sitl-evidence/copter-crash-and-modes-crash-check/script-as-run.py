"""Copter crash_check ('Crash: Disarming') after a motor-failure impact, flown. Simulator only (SITL instance 2, worker 2 of the swarm).

Source read first (ArduCopter/crash_check.cpp, Copter::crash_check): while armed, not land_complete, FS_CRASH_CHECK != 0 and the mode has crash_check_enabled(),
a counter runs only while ALL of these hold at once: filtered accel < 3 m/s/s, lean angle > 15 deg, attitude error angle > 30 deg, groundspeed vector < 10 m/s.
2 s of that (CRASH_CHECK_TRIGGER_SEC) -> STATUSTEXT 'Crash: Disarming: AngErr=..' and disarm(Method::CRASH).
Earlier project runs (single motor failure, GUIDED, 30 m) left the crashed quad armed for the whole watch. Hypothesis from SIM_Aircraft.cpp: SIM_Multicopter's default
ground behaviour GROUND_BEHAVIOR_NO_MOVEMENT zeroes roll/pitch and gyro whenever hagl <= 1 mm, so the lean > 15 deg gate can never hold on the ground in default SITL;
SIM_GND_BEHAV=0 (GROUND_BEHAVIOR_NONE) lets the airframe stay tilted on the ground.

Cases: (default ground, FS_CRASH_CHECK=1), (SIM_GND_BEHAV=0, FS_CRASH_CHECK=1), (SIM_GND_BEHAV=0, FS_CRASH_CHECK=0).
Telemetry used to evaluate the gates: ATTITUDE, ATTITUDE_QUATERNION vs ATTITUDE_TARGET (error angle), LOCAL_POSITION_NED speed, SCALED_IMU accel, EXTENDED_SYS_STATE landed state.

    python3 sitl-copter-crash-check.py <ardupilot tree> <out dir> <custom-gcs dir> [case label ...]
"""
import csv
import json
import math
import os
import socket
import struct
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link, params  # noqa: E402
from pymavlink import mavutil  # noqa: E402

INSTANCE = 2
TCP_PORT = 5760 + 10 * INSTANCE
RC_PORT = 5501 + 10 * INSTANCE
HOME = (-35.363261, 149.165230, 584.0)
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
ALT_M = 30.0
WATCH_S = 60.0
MODES = {0: 'STABILIZE', 2: 'ALT_HOLD', 4: 'GUIDED', 5: 'LOITER', 6: 'RTL', 9: 'LAND'}
LANDED = {0: 'undefined', 1: 'on_ground', 2: 'in_air', 3: 'takeoff', 4: 'landing'}
# (label, SIM_GND_BEHAV or None for default, FS_CRASH_CHECK)
CASES = [('default-ground-fs1', None, 1), ('gndbehav0-fs1', 0, 1), ('gndbehav0-fs0', 0, 0)]


def qerr_deg(a, b):
    d = abs(sum(x * y for x, y in zip(a, b)))
    return math.degrees(2 * math.acos(min(1.0, d)))


class Rig:
    def __init__(self, conn):
        self.c = conn
        self.rc = {'roll': 1500, 'pitch': 1500, 'thr': 1000, 'yaw': 1500}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.t_rc = self.t_hb = self.t_row = 0.0
        self.t0 = time.time()
        self.notes, self.rows = [], []
        self.mode = None
        self.armed = False
        self.alt = self.speed = self.lean = self.err = self.landed = self.thr = self.accel = None
        self.q = self.qt = None
        self.recording = False
        self.crash_text_at = None

    def now(self):
        return time.time() - self.t0

    def note(self, s):
        self.notes.append('t=%6.1f %s' % (self.now(), s))

    def pump(self, secs):
        end = time.time() + secs
        while time.time() < end:
            if time.time() - self.t_rc >= 0.04:
                self.sock.sendto(struct.pack('<16H', self.rc['roll'], self.rc['pitch'], self.rc['thr'], self.rc['yaw'], *([1500] * 12)), ('127.0.0.1', RC_PORT))
                self.t_rc = time.time()
            if time.time() - self.t_hb >= 1.0:
                self.c.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
                self.t_hb = time.time()
            msg = self.c.recv_match(blocking=True, timeout=0.02)
            if msg is not None:
                self.handle(msg)
            if self.recording and time.time() - self.t_row >= 0.1:
                self.t_row = time.time()
                self.rows.append([round(self.now(), 2), MODES.get(self.mode, self.mode), int(self.armed), self.alt, self.speed, self.lean, self.err,
                                  LANDED.get(self.landed, self.landed), self.thr, self.accel])

    def handle(self, msg):
        k = msg.get_type()
        if k == 'STATUSTEXT':
            self.note('vehicle: %s' % msg.text)
            if 'Crash: Disarming' in msg.text and self.crash_text_at is None:
                self.crash_text_at = self.now()
        elif k == 'HEARTBEAT' and msg.get_srcComponent() == 1 and msg.type not in (6, 27):
            if msg.custom_mode != self.mode or flight.is_armed(msg) != self.armed:
                self.note('mode=%s armed=%s' % (MODES.get(msg.custom_mode, msg.custom_mode), flight.is_armed(msg)))
            self.mode, self.armed = msg.custom_mode, flight.is_armed(msg)
        elif k == 'GLOBAL_POSITION_INT':
            self.alt = round(msg.relative_alt / 1000.0, 2)
        elif k == 'LOCAL_POSITION_NED':
            self.speed = round(math.sqrt(msg.vx ** 2 + msg.vy ** 2 + msg.vz ** 2), 2)
        elif k == 'ATTITUDE':
            self.lean = round(math.degrees(math.acos(max(-1.0, min(1.0, math.cos(msg.roll) * math.cos(msg.pitch))))), 1)
        elif k == 'ATTITUDE_QUATERNION':
            self.q = (msg.q1, msg.q2, msg.q3, msg.q4)
        elif k == 'ATTITUDE_TARGET':
            self.qt = tuple(msg.q)
            if self.q is not None:
                self.err = round(qerr_deg(self.q, self.qt), 1)
        elif k == 'SCALED_IMU':
            self.accel = round(math.sqrt(msg.xacc ** 2 + msg.yacc ** 2 + msg.zacc ** 2) / 1000.0 * 9.80665, 2)   # specific force magnitude, m/s/s (1 g at rest)
        elif k == 'EXTENDED_SYS_STATE':
            self.landed = msg.landed_state
        elif k == 'VFR_HUD':
            self.thr = msg.throttle


def stream(conn):
    for mid, us in ((30, 20000), (31, 50000), (83, 50000), (33, 100000), (32, 100000), (26, 100000), (245, 500000), (74, 200000), (0, 100000)):
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, mid, us, 0, 0, 0, 0, 0)


def gates(rows):
    """seconds (at 10 Hz samples) with each gate true, and with lean+err+speed all true, from the ground-contact-agnostic recorded rows"""
    n = lambda f: round(0.1 * sum(1 for r in rows if f(r)), 1)  # noqa: E731
    ok = lambda r: None not in (r[4], r[5], r[6])  # noqa: E731
    return {'samples': len(rows), 'lean_gt15_s': n(lambda r: r[5] is not None and r[5] > 15), 'err_gt30_s': n(lambda r: r[6] is not None and r[6] > 30),
            'speed_lt10_s': n(lambda r: r[4] is not None and r[4] < 10),
            'lean_err_speed_all_s': n(lambda r: ok(r) and r[5] > 15 and r[6] > 30 and r[4] < 10),
            'lean_err_speed_accel_all_s': n(lambda r: ok(r) and r[5] > 15 and r[6] > 30 and r[4] < 10 and r[9] is not None and abs(r[9] - 9.80665) < 3.0),
            'landed_on_ground_s': n(lambda r: r[7] == 'on_ground')}


def run_case(label, gnd, fs_crash):
    work = os.path.expanduser('~/cg-swarm-2-crash-' + label)
    subprocess.call(['rm', '-rf', work])
    os.makedirs(work)
    proc = subprocess.Popen([BIN, '-w', '--model', '+', '-I', str(INSTANCE), '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=work,
                            stdout=open(os.path.join(work, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    r, summary = None, {'case': label}
    try:
        conn, _ = link.connect(TCP_PORT, timeout=120.0)
        r = Rig(conn)
        r.note('case %s: SIM_GND_BEHAV=%s FS_CRASH_CHECK=%d tcp %d rc udp %d' % (label, gnd, fs_crash, TCP_PORT, RC_PORT))
        r.pump(20)
        stream(conn)
        base = link.read_params(conn)
        r.note('defaults: FS_CRASH_CHECK=%s SIM_GND_BEHAV=%s SIM_ENGINE_FAIL=%s SIM_ENGINE_MUL=%s FLTMODE_CH=%s' % tuple(base.get(k) for k in ('FS_CRASH_CHECK', 'SIM_GND_BEHAV', 'SIM_ENGINE_FAIL', 'SIM_ENGINE_MUL', 'FLTMODE_CH')))
        ch = [params.Change('FLTMODE_CH', base.get('FLTMODE_CH'), 0.0), params.Change('FS_CRASH_CHECK', base.get('FS_CRASH_CHECK'), float(fs_crash))]
        if gnd is not None:
            ch.append(params.Change('SIM_GND_BEHAV', base.get('SIM_GND_BEHAV'), float(gnd)))
        bad = [x.name for x in params.write(conn, ch) if not x.ok]
        r.note('params written (rejected %s)' % bad)
        stream(conn)
        r.pump(2)
        flight.set_mode(conn, 'GUIDED', table='copter')
        armed = flight.arm(conn, timeout=120.0)
        r.note('arm: %s' % armed.detail)
        if not armed.ok:
            return r, summary
        conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, ALT_M)
        t = time.time()
        while time.time() - t < 60 and (r.alt is None or r.alt < ALT_M - 1.5):
            r.pump(0.3)
        r.pump(8)
        r.note('hover alt=%s mode=%s' % (r.alt, MODES.get(r.mode)))
        t_fault = r.now()
        r.recording = True
        bad2 = [x.name for x in params.write(conn, [params.Change('SIM_ENGINE_FAIL', base.get('SIM_ENGINE_FAIL'), 1.0)]) if not x.ok]
        r.note('FAULT: SIM_ENGINE_FAIL -> 1 (rejected %s)' % bad2)
        stop_at = None
        while r.now() - t_fault < WATCH_S:
            r.pump(0.1)
            if not r.armed and stop_at is None:
                stop_at = r.now()
            if stop_at is not None and r.now() - stop_at > 4:
                break
        r.recording = False
        post = [x for x in r.rows if x[0] > t_fault + 4]          # after the fall; gates evaluated from 4 s after the fault
        summary.update({'SIM_GND_BEHAV': gnd, 'FS_CRASH_CHECK': fs_crash, 'crash_text_s_after_fault': None if r.crash_text_at is None else round(r.crash_text_at - t_fault, 1),
                        'armed_at_end': r.armed, 'disarmed_s_after_fault': None if stop_at is None else round(stop_at - t_fault, 1), 'gates_after_4s': gates(post),
                        'gates_whole_watch': gates(r.rows),
                        'final_row': r.rows[-1] if r.rows else None})
        r.note('RESULT ' + json.dumps(summary))
    except Exception as e:  # noqa: BLE001
        if r is not None:
            r.note('EXCEPTION %r' % (e,))
    finally:
        proc.terminate()
        try:
            proc.wait(60)
        except Exception:  # noqa: BLE001
            proc.kill()
    return r, summary


def main():
    os.makedirs(OUT, exist_ok=True)
    only = sys.argv[4:]
    summaries = []
    for label, gnd, fs in CASES:
        if only and label not in only:
            continue
        r, s = run_case(label, gnd, fs)
        summaries.append(s)
        if r is not None:
            with open(os.path.join(OUT, label + '-notes.txt'), 'w') as f:
                f.write('\n'.join(r.notes) + '\n')
            with open(os.path.join(OUT, label + '-track.csv'), 'w', newline='') as f:
                w = csv.writer(f)
                w.writerow(['seconds', 'mode', 'armed', 'rel_alt_m', 'speed_ms', 'lean_deg', 'att_error_deg', 'landed_state', 'throttle_pct', 'specific_force_ms2'])
                w.writerows(r.rows)
        print('[crash-check] %s: %s' % (label, json.dumps(s)), flush=True)
    with open(os.path.join(OUT, 'crash-check-summary.json'), 'w') as f:
        json.dump(summaries, f, indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
