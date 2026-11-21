"""Copter FLIP mode, flown: entry gate, flip direction rule, completion and abandon. Simulator only (SITL instance 2, worker 2 of the swarm).

Source read first (ArduCopter/mode_flip.cpp): ModeFlip::init() refuses unless the CURRENT mode's allows_flip() is true (ACRO, ALT_HOLD, FLOWHOLD, STABILIZE),
refuses when either roll or pitch stick is 'high magnitude' (|control_in| >= 4000 of 4500), and picks the direction from the sticks at entry:
pitch_in > 300 -> back, pitch_in < -300 -> forward, else roll_in >= 0 -> ROLL_RIGHT, else ROLL_LEFT. The file header says 'with no pilot input the flip is ROLL_LEFT';
the code gives ROLL_RIGHT for a centred stick. run() ends the flip by set_mode(original mode) after recovery, or on abandon (high stick, timeout 2*360/rate s).

SITL RC input is the UDP '<16H' socket (instance 2 -> port 5501+20), FLTMODE_CH=0 so the mode switch cannot change mode, throttle centred (1500) in flight.

    python3 sitl-copter-flip-mode.py <ardupilot tree> <out dir> <custom-gcs dir> [case label ...]
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
MODES = {'STABILIZE': 0, 'ACRO': 1, 'ALT_HOLD': 2, 'GUIDED': 4, 'LOITER': 5, 'DRIFT': 11, 'SPORT': 13, 'FLIP': 14, 'POSHOLD': 16, 'BRAKE': 17}
NAMES = {v: k for k, v in MODES.items()}
# (label, mode flip is requested from, roll pwm, pitch pwm, abandon_after_s or None)
CASES = [
    ('althold-centred', 'ALT_HOLD', 1500, 1500, None),
    ('althold-centred-repeat', 'ALT_HOLD', 1500, 1500, None),
    ('althold-roll-left', 'ALT_HOLD', 1200, 1500, None),
    ('althold-roll-right', 'ALT_HOLD', 1800, 1500, None),
    ('althold-pitch-back', 'ALT_HOLD', 1500, 1800, None),
    ('althold-pitch-forward', 'ALT_HOLD', 1500, 1200, None),
    ('stabilize-centred', 'STABILIZE', 1500, 1500, None),
    ('acro-centred', 'ACRO', 1500, 1500, None),
    ('althold-high-roll-stick', 'ALT_HOLD', 2000, 1500, None),
    ('loiter-centred', 'LOITER', 1500, 1500, None),
    ('poshold-centred', 'POSHOLD', 1500, 1500, None),
    ('sport-centred', 'SPORT', 1500, 1500, None),
    ('drift-centred', 'DRIFT', 1500, 1500, None),
    ('guided-centred', 'GUIDED', 1500, 1500, None),
    ('althold-abandon-by-stick', 'ALT_HOLD', 1500, 1500, 0.4),
]


class Rig:
    def __init__(self, conn):
        self.c = conn
        self.rc = {'roll': 1500, 'pitch': 1500, 'thr': 1000, 'yaw': 1500}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.t_rc = 0.0
        self.t_hb = 0.0
        self.att = None
        self.alt = None
        self.mode = None
        self.armed = False
        self.rc_seen = None
        self.notes = []
        self.rows = []
        self.t0 = time.time()
        self.record = None   # case label while recording

    def now(self):
        return time.time() - self.t0

    def note(self, s):
        self.notes.append('t=%6.1f %s' % (self.now(), s))

    def pump(self, secs):
        end = time.time() + secs
        while time.time() < end:
            if time.time() - self.t_rc >= 0.04:
                pkt = struct.pack('<16H', self.rc['roll'], self.rc['pitch'], self.rc['thr'], self.rc['yaw'], *([1500] * 12))
                self.sock.sendto(pkt, ('127.0.0.1', RC_PORT))
                self.t_rc = time.time()
            if time.time() - self.t_hb >= 1.0:
                self.c.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
                self.t_hb = time.time()
            msg = self.c.recv_match(blocking=True, timeout=0.02)
            if msg is None:
                continue
            k = msg.get_type()
            if k == 'STATUSTEXT':
                self.note('vehicle: %s' % msg.text)
            elif k == 'HEARTBEAT' and msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                m = msg.custom_mode
                if m != self.mode:
                    self.note('mode=%s armed=%s' % (NAMES.get(m, m), flight.is_armed(msg)))
                self.mode, self.armed = m, flight.is_armed(msg)
            elif k == 'GLOBAL_POSITION_INT':
                self.alt = msg.relative_alt / 1000.0
            elif k == 'RC_CHANNELS':
                self.rc_seen = (msg.chan1_raw, msg.chan2_raw, msg.chan3_raw, msg.chan4_raw)
            elif k == 'ATTITUDE':
                self.att = msg
                if self.record is not None:
                    self.rows.append([self.record, round(self.now(), 3), NAMES.get(self.mode, self.mode), round(math.degrees(msg.roll), 1),
                                      round(math.degrees(msg.pitch), 1), round(math.degrees(msg.rollspeed), 0), round(math.degrees(msg.pitchspeed), 0),
                                      None if self.alt is None else round(self.alt, 1)])

    def set_mode(self, name, settle=1.0):
        self.c.mav.command_long_send(self.c.target_system, self.c.target_component, 176, 0, 1, MODES[name], 0, 0, 0, 0, 0)
        ack = None
        end = time.time() + settle
        while time.time() < end:
            self.pump(0.05)
        return ack


def stream(conn):
    for mid, us in ((30, 20000), (33, 100000), (65, 200000), (0, 100000)):
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, mid, us, 0, 0, 0, 0, 0)


def run_case(r, case, from_mode, roll, pitch, abandon_after):
    label = case
    r.rc.update(roll=1500, pitch=1500, thr=1500)
    if from_mode in ('LOITER', 'POSHOLD', 'GUIDED', 'DRIFT', 'SPORT'):
        pass
    r.set_mode(from_mode, 0.5)
    r.pump(6.0)
    if from_mode == 'GUIDED':
        r.note('GUIDED hover (no sticks used)')
    pre_alt = r.alt
    pre_mode = NAMES.get(r.mode, r.mode)
    r.rc.update(roll=roll, pitch=pitch)
    r.pump(0.8)
    r.note('%s: from %s alt=%.1f, sticks roll=%d pitch=%d (RC_CHANNELS seen %s)' % (label, pre_mode, pre_alt or -1, roll, pitch, r.rc_seen))
    r.record = label
    r.rows.append([label, round(r.now(), 3), 'REQUEST', None, None, None, None, None])
    r.c.mav.command_long_send(r.c.target_system, r.c.target_component, 176, 0, 1, MODES['FLIP'], 0, 0, 0, 0, 0)
    t_req = r.now()
    saw_flip_at, back_at, abandoned_at = None, None, None
    abandon_sent = False
    start_n = len(r.rows)
    while r.now() - t_req < 7.0:
        r.pump(0.05)
        if r.mode == MODES['FLIP'] and saw_flip_at is None:
            saw_flip_at = r.now()
        if saw_flip_at is not None and r.mode != MODES['FLIP'] and back_at is None:
            back_at = r.now()
        if abandon_after is not None and saw_flip_at is not None and not abandon_sent and r.now() - saw_flip_at >= abandon_after:
            r.rc['roll'] = 2000
            abandon_sent = True
            abandoned_at = r.now()
            r.note('%s: roll stick -> 2000 (abandon)' % label)
        if back_at is not None and r.now() - back_at > 2.0:
            break
        if not r.armed:
            r.note('%s: disarmed' % label)
            break
    r.record = None
    seg = [x for x in r.rows[start_n:] if x[3] is not None]
    pk_roll = max(seg, key=lambda x: abs(x[3]))[3] if seg else None
    pk_pitch = max(seg, key=lambda x: abs(x[4]))[4] if seg else None
    pk_rr = max(seg, key=lambda x: abs(x[5]))[5] if seg else None
    pk_pr = max(seg, key=lambda x: abs(x[6]))[6] if seg else None
    alts = [x[7] for x in seg if x[7] is not None]
    summary = {'case': label, 'from_mode': pre_mode, 'roll_pwm': roll, 'pitch_pwm': pitch, 'flip_mode_seen': saw_flip_at is not None,
               'flip_active_s': None if (saw_flip_at is None or back_at is None) else round(back_at - saw_flip_at, 2),
               'mode_after': NAMES.get(r.mode, r.mode), 'peak_roll_rate_dps': pk_rr, 'peak_pitch_rate_dps': pk_pr,
               'peak_abs_roll_deg_signed': pk_roll, 'peak_abs_pitch_deg_signed': pk_pitch,
               'alt_start_m': pre_alt, 'alt_min_m': min(alts) if alts else None, 'alt_end_m': alts[-1] if alts else None,
               'armed_end': r.armed}
    r.note('RESULT ' + json.dumps(summary))
    r.rc.update(roll=1500, pitch=1500, thr=1500)
    # recover: ALT_HOLD and re-climb if we lost too much height
    r.set_mode('ALT_HOLD', 0.5)
    r.pump(5.0)
    if r.alt is not None and r.alt < ALT_M - 8 and r.armed:
        r.rc['thr'] = 1700
        t = time.time()
        while time.time() - t < 20 and r.alt < ALT_M - 1:
            r.pump(0.2)
        r.rc['thr'] = 1500
        r.pump(4.0)
    return summary


def main():
    os.makedirs(OUT, exist_ok=True)
    only = sys.argv[4:]
    work = os.path.expanduser('~/cg-swarm-2-flip')
    subprocess.call(['rm', '-rf', work])
    os.makedirs(work)
    proc = subprocess.Popen([BIN, '-w', '--model', '+', '-I', str(INSTANCE), '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=work,
                            stdout=open(os.path.join(work, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    summaries = []
    r = None
    try:
        conn, _ = link.connect(TCP_PORT, timeout=120.0)
        r = Rig(conn)
        r.note('connected tcp %d, RC udp %d' % (TCP_PORT, RC_PORT))
        r.pump(20)
        stream(conn)
        base = link.read_params(conn)
        r.note('defaults: FLTMODE_CH=%s FS_THR_ENABLE=%s FS_CRASH_CHECK=%s ATC_ANGLE_MAX=%s FLIP_RATE=%s' % (base.get('FLTMODE_CH'), base.get('FS_THR_ENABLE'), base.get('FS_CRASH_CHECK'), base.get('ATC_ANGLE_MAX'), base.get('FLIP_RATE')))
        bad = [x.name for x in params.write(conn, [params.Change('FLTMODE_CH', base.get('FLTMODE_CH'), 0.0)]) if not x.ok]
        r.note('FLTMODE_CH -> 0 (rejected %s)' % bad)
        stream(conn)
        r.pump(2)
        # arm and take off in GUIDED with throttle low (pilot-throttle modes only after take-off)
        flight.set_mode(conn, 'GUIDED', table='copter')
        armed = flight.arm(conn, timeout=120.0)
        r.note('arm: %s' % armed.detail)
        if not armed.ok:
            return
        conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, ALT_M)
        t = time.time()
        while time.time() - t < 60 and (r.alt is None or r.alt < ALT_M - 1.5):
            r.pump(0.3)
        r.note('takeoff alt=%s' % r.alt)
        r.rc['thr'] = 1500
        r.pump(5)
        for label, frm, roll, pitch, ab in CASES:
            if only and label not in only:
                continue
            if not r.armed or r.alt is None or r.alt < 10:
                r.note('skipping %s: armed=%s alt=%s' % (label, r.armed, r.alt))
                continue
            summaries.append(run_case(r, label, frm, roll, pitch, ab))
    except Exception as e:  # noqa: BLE001
        if r is not None:
            r.note('EXCEPTION %r' % (e,))
    finally:
        proc.terminate()
        try:
            proc.wait(60)
        except Exception:  # noqa: BLE001
            proc.kill()
        if r is not None:
            with open(os.path.join(OUT, 'flip-notes.txt'), 'w') as f:
                f.write('\n'.join(r.notes) + '\n')
            with open(os.path.join(OUT, 'flip-track.csv'), 'w', newline='') as f:
                w = csv.writer(f)
                w.writerow(['case', 'seconds', 'mode', 'roll_deg', 'pitch_deg', 'roll_rate_dps', 'pitch_rate_dps', 'rel_alt_m'])
                w.writerows(r.rows)
            with open(os.path.join(OUT, 'flip-summary.json'), 'w') as f:
                json.dump(summaries, f, indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
