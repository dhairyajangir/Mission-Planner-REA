"""Copter GCS-loss failsafe, flown: FS_GCS_ENABLE action map, FS_GCS_TIMEOUT, and the FS_OPTIONS pilot-control exception. Simulator only.

Copter::failsafe_gcs_check (ArduCopter/events.cpp) compares time since the last heartbeat from SYSID_MYGCS against FS_GCS_TIMEOUT (default 5 s) and, past it,
calls failsafe_gcs_on_event, which maps FS_GCS_ENABLE to an action - unless FS_OPTIONS lets the vehicle continue. FS_OPTIONS' default here is 16
(GCS_CONTINUE_IF_PILOT_CONTROL), so in a pilot-controlled mode (LOITER) the failsafe is announced but no action is taken, while in an autopilot mode (GUIDED) it acts.
This flies a Copter 60 m north at 20 m in GUIDED, optionally switches to LOITER, then stops GCS heartbeats (keeping the link open and still reading) and records
time from the last heartbeat sent to the notice, the mode chosen, and the outcome; heartbeats resume CLEAR_AFTER_S after the notice to see what clearing does.

    python3 sitl-copter-gcs-failsafe.py <ardupilot tree> <out dir> <custom-gcs dir> [case label ...]
"""
import csv
import math
import os
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link, params  # noqa: E402
from pymavlink import mavutil  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
TYPE_MASK_POSITION_ONLY = 0b0000111111111000
ALT_M = 20.0
WATCH_S = 70.0
CLEAR_AFTER_S = 12.0
HB_PERIOD_S = 1.0
# (label, FS_GCS_ENABLE, FS_GCS_TIMEOUT, FS_OPTIONS or None to keep the default, mode flown in when heartbeats stop)
CASES = [
    ('rtl-guided', 1, 5, None, 'GUIDED'),
    ('rtl-guided-timeout3', 1, 3, None, 'GUIDED'),
    ('land-guided', 5, 5, None, 'GUIDED'),
    ('smartrtl-guided', 3, 5, None, 'GUIDED'),
    ('brake-or-land-guided', 7, 5, None, 'GUIDED'),
    ('rtl-loiter-default-options', 1, 5, None, 'LOITER'),
    ('rtl-loiter-options0', 1, 5, 0, 'LOITER'),
]
MODE_NAMES = {3: 'AUTO', 4: 'GUIDED', 5: 'LOITER', 6: 'RTL', 9: 'LAND', 17: 'BRAKE', 21: 'SMART_RTL'}


class Heart:
    """Sends a GCS heartbeat (sysid 255, the SYSID_MYGCS default) at most once per HB_PERIOD_S while enabled."""

    def __init__(self, conn):
        self.conn, self.on, self.last_sent = conn, True, 0.0

    def tick(self):
        now = time.time()
        if self.on and now - self.last_sent >= HB_PERIOD_S:
            self.conn.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
            self.last_sent = now


def goto_local(conn, heart, north_m, east_m, alt_m, timeout=60.0, tol_m=4.0):
    begin = time.time()
    last_pos = None
    while time.time() - begin < timeout:
        heart.tick()
        conn.mav.set_position_target_local_ned_send(0, conn.target_system, conn.target_component,
                                                      mavutil.mavlink.MAV_FRAME_LOCAL_NED, TYPE_MASK_POSITION_ONLY,
                                                      north_m, east_m, -alt_m, 0, 0, 0, 0, 0, 0, 0, 0)
        msg = conn.recv_match(type='LOCAL_POSITION_NED', blocking=True, timeout=0.5)
        if msg is None:
            continue
        last_pos = (msg.x, msg.y, msg.z)
        if math.hypot(msg.x - north_m, msg.y - east_m) <= tol_m:
            return True, last_pos
    return False, last_pos


def run_case(label, fs_gcs, timeout_s, fs_options, fly_mode):
    work = os.path.expanduser('~/cg-copter-gcs-failsafe-' + label)
    subprocess.call(['pkill', '-x', 'arducopter'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', work])
    os.makedirs(work)
    notes, track = [], []
    notes.append('case %s: FS_GCS_ENABLE=%d FS_GCS_TIMEOUT=%d FS_OPTIONS=%s flown in %s' % (
        label, fs_gcs, timeout_s, 'default' if fs_options is None else fs_options, fly_mode))
    proc = subprocess.Popen([BIN, '-w', '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=work,
                            stdout=open(os.path.join(work, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        heart = Heart(conn)
        end = time.time() + 20
        while time.time() < end:  # keep the link warm and heartbeats flowing through boot
            heart.tick()
            conn.recv_match(blocking=True, timeout=0.2)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 32, 100000, 0, 0, 0, 0, 0)
        base = link.read_params(conn)
        notes.append('defaults: FS_GCS_ENABLE=%s FS_GCS_TIMEOUT=%s FS_OPTIONS=%s SYSID_MYGCS=%s' % (
            base.get('FS_GCS_ENABLE'), base.get('FS_GCS_TIMEOUT'), base.get('FS_OPTIONS'), base.get('SYSID_MYGCS')))
        flight.set_mode(conn, 'GUIDED', table='copter')
        armed = flight.arm(conn, timeout=120.0)
        notes.append('arm: %s' % armed.detail)
        if not armed.ok:
            return notes, track
        conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, ALT_M)
        conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
        end = time.time() + 25
        while time.time() < end:
            heart.tick()
            conn.recv_match(blocking=True, timeout=0.2)
        ok1, pos1 = goto_local(conn, heart, 60.0, 0.0, ALT_M)
        notes.append('outbound leg (60m north) reached=%s at %s' % (ok1, pos1))
        # The failsafe params are applied only now, in the air, with a heartbeat just before and after each write: with FS_GCS_ENABLE set earlier,
        # the setup steps above (parameter read, arm retries) stop heartbeats for more than 5 s, the failsafe fires on the ground and
        # 'Arm: GCS failsafe on' blocks arming (sitl-evidence/copter-gcs-failsafe/arm-blocked-by-gcs-failsafe-probe.txt).
        # FS_GCS_ENABLE goes last so the timeout clock starts from a fresh heartbeat.
        pending = [params.Change('FS_GCS_TIMEOUT', base.get('FS_GCS_TIMEOUT'), float(timeout_s))]
        if fs_options is not None:
            pending.append(params.Change('FS_OPTIONS', base.get('FS_OPTIONS'), float(fs_options)))
        pending.append(params.Change('FS_GCS_ENABLE', base.get('FS_GCS_ENABLE'), float(fs_gcs)))
        bad = []
        for change in pending:
            heart.last_sent = 0.0
            heart.tick()
            bad += [r.name for r in params.write(conn, [change]) if not r.ok]
        heart.last_sent = 0.0
        heart.tick()
        notes.append('params written in flight: %s (rejected %s)' % ([c.name for c in pending], bad))
        if fly_mode != 'GUIDED':
            res = flight.set_mode(conn, fly_mode, table='copter')
            notes.append('switch to %s: %s' % (fly_mode, res.detail))
            end = time.time() + 5
            while time.time() < end:
                heart.tick()
                conn.recv_match(blocking=True, timeout=0.2)

        heart.on = False
        t0 = heart.last_sent  # the last heartbeat actually sent: the vehicle's timeout counts from here
        t_stop = time.time()
        notes.append('heartbeats stopped; last one sent %.2fs before this line' % (t_stop - t0))
        fs_seen_at, resumed, last_mode = None, False, None
        while time.time() - t0 < WATCH_S:
            msg = conn.recv_match(type=['LOCAL_POSITION_NED', 'STATUSTEXT', 'HEARTBEAT'], blocking=True, timeout=1)
            if msg is not None:
                t = time.time() - t0
                kind = msg.get_type()
                if kind == 'STATUSTEXT':
                    notes.append('t=%5.1f vehicle: %s' % (t, msg.text))
                    if 'GCS Failsafe' in msg.text and 'Cleared' not in msg.text and fs_seen_at is None:
                        fs_seen_at = t
                elif kind == 'LOCAL_POSITION_NED':
                    track.append([round(t, 1), round(msg.x, 1), round(msg.y, 1), round(-msg.z, 1)])
                elif kind == 'HEARTBEAT' and msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                    armed_now = flight.is_armed(msg)
                    if msg.custom_mode != last_mode:
                        notes.append('t=%5.1f mode=%s armed=%s' % (t, MODE_NAMES.get(msg.custom_mode, msg.custom_mode), armed_now))
                        last_mode = msg.custom_mode
                    if not armed_now and t > 5:
                        notes.append('t=%5.1f disarmed, stopping watch' % t)
                        break
            if fs_seen_at is not None and not resumed and time.time() - t0 - fs_seen_at > CLEAR_AFTER_S:
                heart.on = True
                notes.append('t=%5.1f heartbeats resumed' % (time.time() - t0))
                resumed = True
            heart.tick()
        notes.append('time from last heartbeat sent to GCS Failsafe notice: %s' % (None if fs_seen_at is None else round(fs_seen_at, 1)))
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    return notes, track


def main():
    os.makedirs(OUT, exist_ok=True)
    only = sys.argv[4:]
    for label, fs_gcs, timeout_s, fs_options, fly_mode in CASES:
        if only and label not in only:
            continue
        notes, track = run_case(label, fs_gcs, timeout_s, fs_options, fly_mode)
        with open(os.path.join(OUT, label + '-notes.txt'), 'w') as f:
            f.write('\n'.join(notes) + '\n')
        with open(os.path.join(OUT, label + '-track.csv'), 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['seconds', 'north_m', 'east_m', 'alt_m'])
            w.writerows(track)
        print('[gcs-failsafe] %s: %d track rows; last: %s' % (label, len(track), track[-1:]), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
