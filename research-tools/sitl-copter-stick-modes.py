"""Stick-response test of ArduCopter flight modes against a disposable SITL (WSL, pymavlink). Never use with a real vehicle or live link.

For each mode: take off in GUIDED to ~20 m, switch to the mode, hold a known roll stick for HOLD simulated seconds with
RC_CHANNELS_OVERRIDE (pitch/yaw centred, throttle mid), record ATTITUDE (roll, roll rate, yaw rate) at ~20 Hz, release, return
to LOITER. GUIDED_NOGPS is driven with SET_ATTITUDE_TARGET instead of sticks; SYSTEMID is entered with a roll-angle sweep
(SID_AXIS=1) and the roll variance is compared with a hover reference in LOITER.

    python sitl-copter-stick-modes.py <arducopter binary> <outdir>
"""
import csv
import json
import math
import os
import statistics
import subprocess
import sys
import time

from pymavlink import mavutil

HOLD = 1.0     # simulated seconds of stick input
SETTLE = 4.0   # simulated seconds to settle in LOITER between tests


class Link:
    def __init__(self, m):
        self.m = m
        self.att = None
        self.pos = None
        self.hb = None
        self.texts = []
        self.samples = []   # (sim_t, roll_deg, rollspeed_dps, yawspeed_dps)
        self.record = False
        self.rc = None      # roll pwm to hold, None = centred
        self.thr = 1500     # throttle pwm sent with the override
        self.send = False   # RC override is only sent once airborne (centred throttle before arming fails a pre-arm check)

    def sim_t(self):
        return self.att.time_boot_ms / 1000.0 if self.att else 0.0

    def pump(self, secs):
        end = time.time() + secs
        while time.time() < end:
            msg = self.m.recv_match(blocking=True, timeout=0.05)
            self.send_sticks()
            if msg is None:
                continue
            t = msg.get_type()
            if t == 'ATTITUDE':
                self.att = msg
                if self.record:
                    self.samples.append((msg.time_boot_ms / 1000.0, math.degrees(msg.roll), math.degrees(msg.rollspeed), math.degrees(msg.yawspeed)))
            elif t == 'GLOBAL_POSITION_INT':
                self.pos = msg
            elif t == 'HEARTBEAT' and msg.autopilot == 3:
                self.hb = msg
            elif t == 'STATUSTEXT':
                self.texts.append(msg.text)

    def send_sticks(self):
        if not self.send:
            return
        roll =self.rc if self.rc is not None else 1500
        self.m.mav.rc_channels_override_send(self.m.target_system, self.m.target_component, roll, 1500, self.thr, 1500, 0, 0, 0, 0)

    def mode(self):
        if self.hb is None:
            return None
        return {v: k for k, v in self.m.mode_mapping().items()}.get(self.hb.custom_mode)

    def set_mode(self, name):
        self.m.set_mode(self.m.mode_mapping()[name])
        t0 = time.time()
        while time.time() - t0 < 10:
            self.pump(0.2)
            if self.mode() == name:
                return True
        return False

    def sim_wait(self, secs, wall_limit=120):
        start = self.sim_t()
        t0 = time.time()
        while self.sim_t() - start < secs and time.time() - t0 < wall_limit:
            self.pump(0.1)

    def get_param(self, name):
        self.m.mav.param_request_read_send(self.m.target_system, self.m.target_component, name.encode(), -1)
        t0 = time.time()
        while time.time() - t0 < 5:
            msg = self.m.recv_match(type='PARAM_VALUE', blocking=True, timeout=1)
            if msg is not None and msg.param_id.rstrip('\x00') == name:
                return msg.param_value
        return None

    def set_param(self, name, value):
        self.m.mav.param_set_send(self.m.target_system, self.m.target_component, name.encode(), float(value), mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
        self.pump(0.5)


def takeoff(L, alt=20.0):
    L.set_mode('GUIDED')
    if not (L.hb is not None and L.hb.base_mode & 128):
        L.m.arducopter_arm()
        t0 = time.time()
        while time.time() - t0 < 30 and not (L.hb is not None and L.hb.base_mode & 128):
            L.pump(0.5)
    L.m.mav.command_long_send(L.m.target_system, L.m.target_component, mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, alt)
    t0 = time.time()
    while time.time() - t0 < 90:
        L.pump(0.3)
        if L.pos is not None and L.pos.relative_alt / 1000.0 > alt - 1:
            return True
    return False


def alt(L):
    return L.pos.relative_alt / 1000.0 if L.pos else None


def recover(L):
    """back to LOITER, level and at height; re-take-off if too low"""
    L.rc = None
    L.set_mode('LOITER')
    L.sim_wait(SETTLE)
    if alt(L) is None or alt(L) < 10:
        takeoff(L)
        L.set_mode('LOITER')
        L.sim_wait(SETTLE)


def stick_run(L, mode, pwm):
    """enter mode, hold roll pwm for HOLD sim seconds, return metrics"""
    recover(L)
    entered = L.set_mode(mode)
    a0 = alt(L)
    L.sim_wait(1.0)
    L.samples.clear()
    L.record = True
    t_on = L.sim_t()
    L.rc = pwm
    L.sim_wait(HOLD)
    L.rc = None
    L.sim_wait(1.5)
    L.record = False
    held = [s for s in L.samples if t_on <= s[0] <= t_on + HOLD]
    last = [s for s in held if s[0] >= t_on + HOLD - 0.4]
    alt_end = alt(L)
    return {'mode': mode, 'stick_roll_pwm': pwm, 'entered': entered, 'samples': len(held),
            'peak_roll_deg': round(max((s[1] for s in held), key=abs, default=0.0), 2),
            'mean_roll_deg_last_0.4s': round(statistics.mean(s[1] for s in last), 2) if last else None,
            'peak_roll_rate_dps': round(max((s[2] for s in held), key=abs, default=0.0), 1),
            'peak_yaw_rate_dps': round(max((s[3] for s in held), key=abs, default=0.0), 1),
            'alt_before_m': round(a0, 1) if a0 is not None else None, 'alt_after_m': round(alt_end, 1) if alt_end is not None else None}


def main():
    binary, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    log = open(os.path.join(outdir, 'sitl.log'), 'w')
    proc = subprocess.Popen([binary, '-w', '-M', '+', '-I', '6', '-s', '5', '--home', '-35.363261,149.165230,584,0'], cwd=outdir,
                            stdout=log, stderr=subprocess.STDOUT)
    rows, events = [], []
    try:
        m = None
        for _ in range(40):
            try:
                m = mavutil.mavlink_connection('tcp:127.0.0.1:5820', autoreconnect=False)
                break
            except Exception:
                time.sleep(0.5)
        m.wait_heartbeat(timeout=20)
        L = Link(m)
        m.mav.request_data_stream_send(m.target_system, m.target_component, mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1)
        m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0, 30, 50000, 0, 0, 0, 0, 0)
        t0 = time.time()
        while time.time() - t0 < 150:
            L.pump(0.5)
            if L.pos is not None and L.pos.lat != 0 and any('using GPS' in t or 'EKF3 IMU0 is using' in t for t in L.texts):
                break
        params = {n: L.get_param(n) for n in ('ATC_ANGLE_MAX', 'ACRO_RP_RATE', 'ACRO_RP_EXPO', 'RC1_DZ', 'ACRO_Y_RATE', 'MOT_THST_HOVER')}
        events.append(('params', params))
        if not takeoff(L):
            raise SystemExit('takeoff failed: %s' % L.texts[-5:])
        L.send = True
        events.append(('airborne_m', alt(L)))
        cases = [('STABILIZE', 1700), ('ALT_HOLD', 1700), ('SPORT', 1600), ('SPORT', 1700), ('ACRO', 1600), ('ACRO', 1700),
                 ('DRIFT', 1700), ('DRIFT', 1300)]
        for mode, pwm, attempt in [(m_, p_, a_) for (m_, p_) in cases for a_ in (1, 2, 3)]:
            row = stick_run(L, mode, pwm)
            row['attempt'] = attempt
            if mode in ('STABILIZE', 'ALT_HOLD') and params.get('RC1_DZ') is not None:
                dz = params['RC1_DZ']
                # ATC_ANGLE_MAX is reported by this build in degrees (read as 30); predicted lean angle = stick fraction after the deadzone * ATC_ANGLE_MAX
                amax = params.get('ATC_ANGLE_MAX') or 30.0
                row['predicted_angle_deg'] = round(((pwm - 1500 - dz) / (500.0 - dz)) * amax, 2)
            rows.append(row)
            print(row, flush=True)
        # GUIDED_NOGPS: attitude target, roll 10 degrees for HOLD s, hover thrust 0.5
        recover(L)
        entered = L.set_mode('GUIDED_NOGPS')
        L.sim_wait(1.0)
        L.samples.clear()
        L.record = True
        t_on = L.sim_t()
        q = [math.cos(math.radians(10) / 2), math.sin(math.radians(10) / 2), 0, 0]
        end = L.sim_t() + 3.0
        while L.sim_t() < end:
            m.mav.set_attitude_target_send(0, m.target_system, m.target_component, 0b00000111, q, 0, 0, 0, 0.5)
            L.pump(0.1)
        L.record = False
        last = [s for s in L.samples if s[0] >= end - 0.6]
        rows.append({'mode': 'GUIDED_NOGPS', 'stick_roll_pwm': 'SET_ATTITUDE_TARGET roll 10 deg', 'entered': entered, 'samples': len(L.samples),
                     'peak_roll_deg': round(max((s[1] for s in L.samples), key=abs, default=0.0), 2),
                     'mean_roll_deg_last_0.4s': round(statistics.mean(s[1] for s in last), 2) if last else None,
                     'alt_before_m': None, 'alt_after_m': round(alt(L), 1) if alt(L) is not None else None})
        print(rows[-1], flush=True)
        # SYSTEMID: roll-angle chirp (SID_AXIS=1) vs LOITER hover reference
        recover(L)
        L.samples.clear()
        L.record = True
        L.sim_wait(6.0)
        L.record = False
        ref = statistics.pstdev([s[1] for s in L.samples]) if len(L.samples) > 5 else None
        for n, v in (('SID_AXIS', 1), ('SID_MAGNITUDE', 5), ('SID_F_START_HZ', 1), ('SID_F_STOP_HZ', 8), ('SID_T_FADE_IN', 1), ('SID_T_REC', 12), ('SID_T_FADE_OUT', 1)):
            L.set_param(n, v)
        # attitude-axis System ID can only be entered from a mode with manual throttle (ArduCopter/mode_systemid.cpp:100-102):
        # enter it from STABILIZE with throttle near hover, not from LOITER
        L.thr = 1400
        L.set_mode('STABILIZE')
        L.sim_wait(0.5)
        entered = L.set_mode('SYSTEMID')
        L.samples.clear()
        L.record = True
        L.sim_wait(10.0)
        L.record = False
        L.thr = 1500
        sid = statistics.pstdev([s[1] for s in L.samples]) if len(L.samples) > 5 else None
        rows.append({'mode': 'SYSTEMID', 'stick_roll_pwm': 'SID_AXIS=1 5 deg 1-8 Hz', 'entered': entered, 'samples': len(L.samples),
                     'peak_roll_deg': round(max((s[1] for s in L.samples), key=abs, default=0.0), 2),
                     'mean_roll_deg_last_0.4s': None, 'alt_before_m': None, 'alt_after_m': round(alt(L), 1) if alt(L) is not None else None,
                     'predicted_angle_deg': 'roll stdev loiter hover %s vs systemid %s' % (round(ref, 3) if ref is not None else None, round(sid, 3) if sid is not None else None)})
        print(rows[-1], flush=True)
        events.append(('texts', L.texts[-8:]))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        log.close()
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(os.path.join(outdir, 'copter-stick-modes.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, keys, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    json.dump({'events': events, 'rows': rows}, open(os.path.join(outdir, 'copter-stick-modes.json'), 'w'), indent=1, default=str)


if __name__ == '__main__':
    main()
