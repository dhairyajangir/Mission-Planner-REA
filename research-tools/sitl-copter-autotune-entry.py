"""Copter AUTOTUNE mode entry conditions, flown. Simulator only (SITL instance 2, worker 2 of the swarm).

Source read first (ArduCopter/mode_autotune.cpp AutoTune::init, libraries/AC_AutoTune/AC_AutoTune.cpp init_internals/stop):
 * entry refused unless the CURRENT mode's allows_autotune() is true: only ALT_HOLD, LOITER, POSHOLD and STABILIZE override it (mode.h).
 * entry refused when ap.throttle_zero (debounced pilot throttle, THROTTLE_ZERO_DEBOUNCE_TIME_MS, cleared the moment control_in > 0).
 * entry refused unless armed && auto_armed && !land_complete.
 * accepted -> 'AutoTune: Started' (TuneMode UNINITIALISED/FAILED) ; leaving the mode -> exit() -> stop() -> 'AutoTune: Stopped' and original gains reloaded; re-entry while the tune is unfinished
   (TuneMode::TUNING) prints 'AutoTune: Started' again and restarts the step from WAITING_FOR_LEVEL.
Custom-GCS-Prototype-Trace.md already shows AUTOTUNE refused while disarmed on the ground ('init failed'); this run covers the flying and armed-on-ground cases.

SITL RC input is the UDP '<16H' socket (instance 2 -> port 5521), FLTMODE_CH=0, throttle centred (1500) in flight.
Observed per request: COMMAND_ACK result of MAV_CMD_DO_SET_MODE, HEARTBEAT mode after 2 s, STATUSTEXT, and (when accepted) 6 s of attitude/altitude.

    python3 sitl-copter-autotune-entry.py <ardupilot tree> <out dir> <custom-gcs dir>
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
ALT_M = 25.0
MODES = {'STABILIZE': 0, 'ACRO': 1, 'ALT_HOLD': 2, 'GUIDED': 4, 'LOITER': 5, 'RTL': 6, 'DRIFT': 11, 'SPORT': 13, 'AUTOTUNE': 15, 'POSHOLD': 16, 'BRAKE': 17}
NAMES = {v: k for k, v in MODES.items()}
AIR_FROM = ['ALT_HOLD', 'STABILIZE', 'LOITER', 'POSHOLD', 'GUIDED', 'SPORT', 'DRIFT', 'ACRO', 'BRAKE']


class Rig:
    def __init__(self, conn):
        self.c = conn
        self.rc = {'roll': 1500, 'pitch': 1500, 'thr': 1000, 'yaw': 1500}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.t_rc = self.t_hb = 0.0
        self.t0 = time.time()
        self.notes, self.rows, self.acks, self.texts = [], [], [], []
        self.mode = None
        self.armed = False
        self.alt = None
        self.att = None
        self.case = None
        self.landed = None
        self.vfr_thr = None
        self.rc3_seen = None

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
            if msg is None:
                continue
            k = msg.get_type()
            if k == 'STATUSTEXT':
                self.note('vehicle: %s' % msg.text)
                self.texts.append((self.now(), msg.text))
            elif k == 'COMMAND_ACK' and msg.command == 176:
                self.acks.append((self.now(), msg.result))
            elif k == 'HEARTBEAT' and msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                m = msg.custom_mode
                if m != self.mode:
                    self.note('mode=%s armed=%s' % (NAMES.get(m, m), flight.is_armed(msg)))
                self.mode, self.armed = m, flight.is_armed(msg)
            elif k == 'EXTENDED_SYS_STATE':
                self.landed = msg.landed_state
            elif k == 'VFR_HUD':
                self.vfr_thr = msg.throttle
            elif k == 'RC_CHANNELS':
                self.rc3_seen = msg.chan3_raw
            elif k == 'GLOBAL_POSITION_INT':
                self.alt = msg.relative_alt / 1000.0
            elif k == 'ATTITUDE':
                self.att = msg
                if self.case is not None:
                    self.rows.append([self.case, round(self.now(), 3), NAMES.get(self.mode, self.mode), round(math.degrees(msg.roll), 1),
                                      round(math.degrees(msg.pitch), 1), round(math.degrees(msg.rollspeed), 0), round(math.degrees(msg.pitchspeed), 0),
                                      None if self.alt is None else round(self.alt, 2), self.rc['thr'], self.landed, self.vfr_thr])

    def request(self, name):
        n_ack, n_txt = len(self.acks), len(self.texts)
        self.c.mav.command_long_send(self.c.target_system, self.c.target_component, 176, 0, 1, MODES[name], 0, 0, 0, 0, 0)
        self.pump(2.0)
        return {'acks': [a[1] for a in self.acks[n_ack:]], 'texts': [t[1] for t in self.texts[n_txt:]], 'mode_after': NAMES.get(self.mode, self.mode)}

    def set_mode(self, name, settle=1.0):
        self.c.mav.command_long_send(self.c.target_system, self.c.target_component, 176, 0, 1, MODES[name], 0, 0, 0, 0, 0)
        self.pump(settle)


def stream(conn):
    for mid, us in ((30, 20000), (33, 100000), (65, 200000), (0, 100000), (245, 100000), (74, 100000)):
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, mid, us, 0, 0, 0, 0, 0)


def recover(r):
    r.rc.update(roll=1500, pitch=1500, thr=1500)
    r.set_mode('ALT_HOLD', 0.5)
    r.pump(3.0)
    if r.alt is not None and r.armed:
        t = time.time()
        if r.alt < ALT_M - 6:
            r.rc['thr'] = 1700
            while time.time() - t < 25 and r.alt < ALT_M - 1:
                r.pump(0.2)
        elif r.alt > ALT_M + 8:
            r.rc['thr'] = 1300
            while time.time() - t < 25 and r.alt > ALT_M + 1:
                r.pump(0.2)
        r.rc['thr'] = 1500
        r.pump(3.0)


def tune_request(r, label, from_mode, note=''):
    """Request AUTOTUNE now; if accepted watch 6 s then leave to ALT_HOLD and record the exit texts."""
    r.case = label
    pre = {'from_mode_actual': NAMES.get(r.mode, r.mode), 'alt_before': r.alt, 'thr_pwm': r.rc['thr'], 'rc3_seen_by_vehicle': r.rc3_seen,
           'landed_state_before(1=ground,2=air)': r.landed, 'vfr_throttle_pct_before': r.vfr_thr, 'armed_before': r.armed}
    res = r.request('AUTOTUNE')
    res.update(case=label, requested_from=from_mode, note=note, **pre)
    res['accepted'] = r.mode == MODES['AUTOTUNE']
    res['armed_after_request_2s'] = r.armed
    if res['accepted']:
        n0, n1 = len(r.rows), len(r.texts)
        r.pump(6.0)
        seg = [x for x in r.rows[n0:] if x[3] is not None]
        res['tune_6s'] = {'peak_abs_roll_deg': max(abs(x[3]) for x in seg), 'peak_abs_pitch_deg': max(abs(x[4]) for x in seg),
                          'alt_min': min(x[7] for x in seg if x[7] is not None), 'alt_max': max(x[7] for x in seg if x[7] is not None), 'texts': [t[1] for t in r.texts[n1:]]}
        n2 = len(r.texts)
        r.set_mode('ALT_HOLD', 1.5)
        res['exit_texts'] = [t[1] for t in r.texts[n2:]]
        res['mode_after_exit'] = NAMES.get(r.mode, r.mode)
    r.note('RESULT ' + json.dumps(res))
    r.case = None
    return res


def main():
    os.makedirs(OUT, exist_ok=True)
    work = os.path.expanduser('~/cg-swarm-2-autotune')
    subprocess.call(['rm', '-rf', work])
    os.makedirs(work)
    proc = subprocess.Popen([BIN, '-w', '--model', '+', '-I', str(INSTANCE), '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=work,
                            stdout=open(os.path.join(work, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    results, r = [], None
    try:
        conn, _ = link.connect(TCP_PORT, timeout=120.0)
        r = Rig(conn)
        r.note('connected tcp %d, RC udp %d' % (TCP_PORT, RC_PORT))
        r.pump(20)
        stream(conn)
        base = link.read_params(conn)
        r.note('defaults: FLTMODE_CH=%s AUTOTUNE_AXES=%s AUTOTUNE_AGGR=%s AUTOTUNE_MIN_D=%s FS_THR_ENABLE=%s' % (
            base.get('FLTMODE_CH'), base.get('AUTOTUNE_AXES'), base.get('AUTOTUNE_AGGR'), base.get('AUTOTUNE_MIN_D'), base.get('FS_THR_ENABLE')))
        params.write(conn, [params.Change('FLTMODE_CH', base.get('FLTMODE_CH'), 0.0)])
        stream(conn)
        r.pump(2)
        # armed on the ground in STABILIZE
        r.set_mode('STABILIZE', 1.0)
        armed = flight.arm(conn, timeout=120.0)
        r.note('arm in STABILIZE: %s' % armed.detail)
        if not armed.ok:
            return 1
        r.pump(3.0)
        for thr in (1000, 1050, 1100, 1200):
            if not r.armed:
                r.rc['thr'] = 1000
                r.set_mode('STABILIZE', 1.0)
                armed = flight.arm(conn, timeout=60.0)
                r.note('re-arm for ground case thr=%d: %s' % (thr, armed.detail))
                r.pump(3.0)
            r.set_mode('STABILIZE', 0.5)
            r.rc['thr'] = thr
            r.pump(4.0)
            results.append(tune_request(r, 'ground-armed-stabilize-thr%d' % thr, 'STABILIZE', 'armed on ground (alt about 0), throttle %d' % thr))
            r.rc['thr'] = 1000
            r.set_mode('STABILIZE', 0.5)
            r.pump(2.0)
        if not r.armed:
            r.rc['thr'] = 1000
            r.set_mode('STABILIZE', 1.0)
            armed = flight.arm(conn, timeout=60.0)
            r.note('re-arm for takeoff: %s' % armed.detail)
            if not armed.ok:
                return 1
        r.rc['thr'] = 1000
        r.set_mode('GUIDED', 1.0)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, ALT_M)
        t = time.time()
        while time.time() - t < 60 and (r.alt is None or r.alt < ALT_M - 1.5):
            r.pump(0.3)
        r.note('takeoff alt=%s' % r.alt)
        r.rc['thr'] = 1500
        r.pump(5)
        for frm in AIR_FROM:
            if not r.armed or r.alt is None or r.alt < 8:
                r.note('skipping %s: armed=%s alt=%s' % (frm, r.armed, r.alt))
                continue
            r.rc.update(roll=1500, pitch=1500, thr=1500)
            r.set_mode(frm, 0.5)
            r.pump(4.0)
            results.append(tune_request(r, 'air-from-%s' % frm.lower(), frm, 'flying, throttle 1500'))
            recover(r)
        # throttle_zero gate in the air
        for frm in ('ALT_HOLD', 'LOITER'):
            r.rc.update(roll=1500, pitch=1500, thr=1500)
            r.set_mode(frm, 0.5)
            r.pump(4.0)
            r.rc['thr'] = 1000
            r.pump(1.5)
            results.append(tune_request(r, 'air-from-%s-thr1000-1.5s' % frm.lower(), frm, 'throttle stick held at 1000 for 1.5 s before the request (debounce window passed), held through the request'))
            recover(r)
        # re-entry after an accepted entry, from ALT_HOLD twice in a row
        for i in (1, 2):
            r.rc.update(roll=1500, pitch=1500, thr=1500)
            r.set_mode('ALT_HOLD', 0.5)
            r.pump(3.0)
            results.append(tune_request(r, 'air-reentry-%d' % i, 'ALT_HOLD', 'repeat entry from ALT_HOLD after the earlier accepted entry/exit'))
            recover(r)
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
            with open(os.path.join(OUT, 'autotune-notes.txt'), 'w') as f:
                f.write('\n'.join(r.notes) + '\n')
            with open(os.path.join(OUT, 'autotune-track.csv'), 'w', newline='') as f:
                w = csv.writer(f)
                w.writerow(['case', 'seconds', 'mode', 'roll_deg', 'pitch_deg', 'roll_rate_dps', 'pitch_rate_dps', 'rel_alt_m', 'thr_pwm', 'landed_state', 'vfr_throttle_pct'])
                w.writerows(r.rows)
            with open(os.path.join(OUT, 'autotune-summary.json'), 'w') as f:
                json.dump(results, f, indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
