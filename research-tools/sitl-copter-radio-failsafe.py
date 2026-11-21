"""Copter radio (RC) failsafe, flown: FS_THR_ENABLE action matrix and the two ways SITL can trigger it. Simulator only.

Copter::read_radio (ArduCopter/radio.cpp) has two independent triggers for failsafe.radio:
  * no RC frame for RC_FS_TIMEOUT seconds (SITL: SIM_RC_FAIL=1, no pulses), and
  * three consecutive throttle readings at or below FS_THR_VALUE (SITL: SIM_RC_FAIL=2, throttle below FS_THR_VALUE).
Copter::failsafe_radio_on_event (ArduCopter/events.cpp) then maps FS_THR_ENABLE to an action. This flies a Copter 60 m north in GUIDED at 20 m,
injects the RC fault with SIM_RC_FAIL, and records time-to-"Radio Failsafe", the mode chosen, the return/landing track, and what clearing the fault does.

    python3 sitl-copter-radio-failsafe.py <ardupilot tree> <out dir> <custom-gcs dir> [case label ...]
"""
import csv
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

HOME = (-35.363261, 149.165230, 584.0)
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
TYPE_MASK_POSITION_ONLY = 0b0000111111111000
ALT_M = 20.0
WATCH_S = 75.0
CLEAR_AFTER_S = 12.0  # clear the fault this long after the failsafe action is observed, to see what clearing does
KICK_AFTER_CLEAR_S = 6.0  # for kick cases: seconds after clearing SIM_RC_FAIL before one UDP RC packet is sent to SITL's RC input
RC_UDP_PORT = 5501  # AP_RCProtocol_UDP's SITL RC input socket
# (label, FS_THR_ENABLE, SIM_RC_FAIL, send one UDP RC packet after clearing)
CASES = [
    ('rtl-no-pulses', 1, 1, False),
    ('rtl-low-throttle', 1, 2, False),
    ('land-low-throttle', 3, 2, False),
    ('smartrtl-no-pulses', 4, 1, False),
    ('rtl-low-throttle-udp-kick', 1, 2, True),
]
MODE_NAMES = {3: 'AUTO', 4: 'GUIDED', 5: 'LOITER', 6: 'RTL', 9: 'LAND', 17: 'BRAKE', 21: 'SMART_RTL'}


def goto_local(conn, north_m, east_m, alt_m, timeout=60.0, tol_m=4.0):
    begin = time.time()
    last_pos = None
    while time.time() - begin < timeout:
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


def run_case(label, fs_thr, rc_fail, kick):
    work = os.path.expanduser('~/cg-copter-radio-failsafe-' + label)
    subprocess.call(['pkill', '-x', 'arducopter'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', work])
    os.makedirs(work)
    notes, track = [], []
    notes.append('case %s: FS_THR_ENABLE=%d SIM_RC_FAIL=%d' % (label, fs_thr, rc_fail))
    proc = subprocess.Popen([BIN, '-w', '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=work,
                            stdout=open(os.path.join(work, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        time.sleep(20)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 32, 100000, 0, 0, 0, 0, 0)
        base = link.read_params(conn)
        notes.append('defaults: FS_THR_ENABLE=%s FS_THR_VALUE=%s RC_FS_TIMEOUT=%s SIM_RC_FAIL=%s FS_OPTIONS=%s' % (
            base.get('FS_THR_ENABLE'), base.get('FS_THR_VALUE'), base.get('RC_FS_TIMEOUT'), base.get('SIM_RC_FAIL'),
            base.get('FS_OPTIONS')))
        bad = [r.name for r in params.write(conn, [params.Change('FS_THR_ENABLE', base.get('FS_THR_ENABLE'), float(fs_thr))])
               if not r.ok]
        notes.append('FS_THR_ENABLE -> %d (rejected %s)' % (fs_thr, bad))

        flight.set_mode(conn, 'GUIDED', table='copter')
        armed = flight.arm(conn, timeout=120.0)
        notes.append('arm: %s' % armed.detail)
        if not armed.ok:
            return notes, track
        conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, ALT_M)
        conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
        time.sleep(25.0)
        ok1, pos1 = goto_local(conn, 60.0, 0.0, ALT_M)
        notes.append('outbound leg (60m north) reached=%s at %s' % (ok1, pos1))

        t0 = time.time()
        bad2 = [r.name for r in params.write(conn, [params.Change('SIM_RC_FAIL', base.get('SIM_RC_FAIL'), float(rc_fail))])
                if not r.ok]
        notes.append('t=%5.1f SIM_RC_FAIL -> %d (rejected %s)' % (time.time() - t0, rc_fail, bad2))

        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 65, 200000, 0, 0, 0, 0, 0)  # RC_CHANNELS at 5 Hz
        fs_seen_at, cleared, cleared_at, kicked, last_rc_note = None, False, None, False, -10.0
        last_mode = None
        while time.time() - t0 < WATCH_S:
            msg = conn.recv_match(type=['LOCAL_POSITION_NED', 'STATUSTEXT', 'HEARTBEAT', 'RC_CHANNELS'], blocking=True, timeout=1)
            if msg is not None:
                t = time.time() - t0
                kind = msg.get_type()
                if kind == 'STATUSTEXT':
                    notes.append('t=%5.1f vehicle: %s' % (t, msg.text))
                    if 'Radio Failsafe' in msg.text and 'Cleared' not in msg.text and fs_seen_at is None:
                        fs_seen_at = t
                elif kind == 'RC_CHANNELS':
                    if t - last_rc_note >= 3.0:
                        notes.append('t=%5.1f RC_CHANNELS chan1=%s chan3=%s' % (t, msg.chan1_raw, msg.chan3_raw))
                        last_rc_note = t
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
            if fs_seen_at is not None and not cleared and time.time() - t0 - fs_seen_at > CLEAR_AFTER_S:
                params.write(conn, [params.Change('SIM_RC_FAIL', float(rc_fail), 0.0)])
                notes.append('t=%5.1f cleared SIM_RC_FAIL -> 0' % (time.time() - t0))
                cleared, cleared_at = True, time.time() - t0
            if kick and cleared and not kicked and time.time() - t0 - cleared_at > KICK_AFTER_CLEAR_S:
                pkt = struct.pack('<16H', *([1500, 1500, 1100, 1500] + [1500] * 12))
                socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(pkt, ('127.0.0.1', RC_UDP_PORT))
                notes.append('t=%5.1f sent one UDP RC packet (chan3=1100) to port %d' % (time.time() - t0, RC_UDP_PORT))
                kicked = True
        notes.append('time to Radio Failsafe notice: %s' % (None if fs_seen_at is None else round(fs_seen_at, 1)))
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
    for label, fs_thr, rc_fail, kick in CASES:
        if only and label not in only:
            continue
        notes, track = run_case(label, fs_thr, rc_fail, kick)
        with open(os.path.join(OUT, label + '-notes.txt'), 'w') as f:
            f.write('\n'.join(notes) + '\n')
        with open(os.path.join(OUT, label + '-track.csv'), 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['seconds', 'north_m', 'east_m', 'alt_m'])
            w.writerows(track)
        print('[radio-failsafe] %s: %d track rows; last: %s' % (label, len(track), track[-1:]), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
