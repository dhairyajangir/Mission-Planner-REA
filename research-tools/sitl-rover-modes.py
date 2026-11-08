"""Armed mode-behaviour test against a disposable Rover SITL (WSL, pymavlink). Never use with a real vehicle or live link.

Sequence: wait for GPS/EKF, arm in MANUAL, then for each mode request it, hold steering mid and throttle forward (1650) with
RC_CHANNELS_OVERRIDE (throttle mid), watch WINDOW simulated seconds of GLOBAL_POSITION_INT, record altitude and drift,
return to LOITER. Finally RTL and wait for landing/disarm (LAND as fallback).

    python sitl-copter-air-modes.py <arducopter binary> <outdir>
"""
import csv
import json
import math
import os
import subprocess
import sys
import time

from pymavlink import mavutil

WINDOW = 8.0   # simulated seconds per mode
MODES = ['MANUAL', 'ACRO', 'STEERING', 'HOLD', 'SIMPLE', 'LOITER', 'CIRCLE', 'GUIDED', 'RTL']
M2 = 1.0 / 1e7 * 111319.5


class Link:
    def __init__(self, m):
        self.m = m
        self.pos = None
        self.texts = []
        self.hb = None
        self.hold = False   # keep sending centred sticks during every wait once airborne

    def pump(self, secs=0.0):
        end = time.time() + secs
        while True:
            msg = self.m.recv_match(blocking=secs > 0, timeout=max(0.01, end - time.time()) if secs > 0 else 0)
            if msg is None:
                if secs <= 0 or time.time() >= end:
                    return
                continue
            if self.hold:
                self.sticks()
            t = msg.get_type()
            if t == 'GLOBAL_POSITION_INT':
                self.pos = msg
            elif t == 'HEARTBEAT' and msg.autopilot == 3:
                self.hb = msg
            elif t == 'STATUSTEXT':
                self.texts.append(msg.text)
            if time.time() >= end:
                return

    def sticks(self):
        self.m.mav.rc_channels_override_send(self.m.target_system, self.m.target_component, 1500, 0, 1650, 1500, 0, 0, 0, 0)

    def set_mode(self, mode):
        self.m.set_mode(self.m.mode_mapping()[mode])


def horiz(a, b):
    dx = (b.lat - a.lat) * M2
    dy = (b.lon - a.lon) * M2 * math.cos(math.radians(a.lat / 1e7))
    return math.hypot(dx, dy)


def main():
    binary, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    log = open(os.path.join(outdir, 'sitl.log'), 'w')
    proc = subprocess.Popen([binary, '-w', '-M', 'rover', '-I', '4', '-s', '5', '--home', '-35.363261,149.165230,584,0'], cwd=outdir,
                            stdout=log, stderr=subprocess.STDOUT)
    rows, events = [], []
    try:
        m = None
        for _ in range(40):
            try:
                m = mavutil.mavlink_connection('tcp:127.0.0.1:5800', autoreconnect=False)
                break
            except Exception:
                time.sleep(0.5)
        m.wait_heartbeat(timeout=20)
        L = Link(m)
        m.mav.request_data_stream_send(m.target_system, m.target_component, mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1)
        # wait for a position estimate
        t0 = time.time()
        while time.time() - t0 < 120:
            L.pump(0.5)
            if L.pos is not None and L.pos.lat != 0 and any('using GPS' in t or 'EKF3 IMU0 is using' in t for t in L.texts):
                break
        events.append(('ready', L.texts[-3:]))
        L.set_mode('MANUAL')
        L.pump(1)
        m.arducopter_arm()
        t0 = time.time()
        while time.time() - t0 < 30 and not (L.hb is not None and L.hb.base_mode & 128):
            L.pump(0.5)
        armed = bool(L.hb is not None and L.hb.base_mode & 128)
        events.append(('armed', armed, L.texts[-3:]))
        if not armed:
            raise SystemExit('could not arm: %s' % L.texts[-5:])
        events.append(('armed_on_ground', L.pos.relative_alt / 1000.0 if L.pos else None))
        L.hold = True
        for mode in MODES:
            L.texts.clear()
            L.set_mode(mode)
            start = None
            first = None
            alts, spd = [], []
            wall_end = time.time() + 120
            while time.time() < wall_end:
                L.pump(0.1)
                L.sticks()
                p = L.pos
                if p is None:
                    continue
                if start is None:
                    start, first = p.time_boot_ms, p
                alts.append(p.relative_alt / 1000.0)
                spd.append(math.hypot(p.vx, p.vy) / 100.0)
                if (p.time_boot_ms - start) / 1000.0 >= WINDOW:
                    break
            last = L.pos
            hbmode = None
            if L.hb is not None:
                hbmode = {v: k for k, v in m.mode_mapping().items()}.get(L.hb.custom_mode)
            rows.append({'mode': mode, 'reported_mode': hbmode, 'entered': hbmode == mode, 'sim_seconds': round((last.time_boot_ms - start) / 1000.0, 1),
                         'alt_start_m': round(alts[0], 2), 'alt_end_m': round(alts[-1], 2), 'alt_min_m': round(min(alts), 2), 'alt_max_m': round(max(alts), 2),
                         'drift_start_to_end_m': round(horiz(first, last), 2), 'max_ground_speed_ms': round(max(spd), 2),
                         'statustext': ' | '.join(L.texts)[:160]})
            print(rows[-1], flush=True)
            L.set_mode('HOLD')
            L.pump(1.5)
        # return home
        L.texts.clear()
        L.set_mode('RTL')
        t0 = time.time()
        while time.time() - t0 < 300:
            L.pump(0.5)
            L.sticks()
            if L.hb is not None and not (L.hb.base_mode & 128):
                break
        events.append(('rtl_finished_disarmed', bool(L.hb is not None and not (L.hb.base_mode & 128)), L.texts[-4:],
                       L.pos.relative_alt / 1000.0 if L.pos else None))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        log.close()
    with open(os.path.join(outdir, 'copter-air-modes.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, list(rows[0].keys()) if rows else ['mode'], lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    json.dump({'events': events, 'rows': rows}, open(os.path.join(outdir, 'copter-air-modes.json'), 'w'), indent=1, default=str)


if __name__ == '__main__':
    main()
