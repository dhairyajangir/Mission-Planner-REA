"""The mid-flight terrain failsafe (ArduCopter/events.cpp failsafe_terrain_check/_on_event, FS_TERRAIN_TIMEOUT_MS 5000 -> RTL) was never reached by sitl-terrain-failsafe.py:
AP_Arming::terrain_checks blocks arming for good whenever the *uploaded mission* contains any terrain-relative item whose data cannot be resolved (AP_Terrain::pre_arm_checks
requires next_mission_index == 0, i.e. every terrain-relative mission item already has data, not just the current/home position) - that holds regardless of whether the bad
waypoint is near or far, so a mission-based test can never reach the mid-flight path. A live GUIDED-mode command is not checked by AP_Arming at all: this test arms with no
mission uploaded (MAV_CMD_NAV_TAKEOFF straight into GUIDED, the same technique sitl-guided-offboard-control.py's copter_position() uses), then once airborne sends one
SET_POSITION_TARGET_GLOBAL_INT in MAV_FRAME_GLOBAL_TERRAIN_ALT_INT toward a location with no cached tile: the pinned snapshot's terrain/ tree has a real tile for home
(S36E149.DAT) and an empty, 0-byte neighbour (S36E148.DAT) about 15 km west across the tile boundary (lon 149.0); only S36E149.DAT is copied in, so crossing into the S36E148
area means AP_Terrain opens a fresh, genuinely empty file there (O_RDWR|O_CREAT) - a real SRTM-void shape, not a corrupted file. Copter, SIM_SPEEDUP raised to keep the flight
time bounded. Simulator only (WSL, pymavlink, the custom-gcs library).

    python3 sitl-terrain-failsafe-midflight.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
import csv
import math
import os
import shutil
import subprocess
import sys
import time

from pymavlink import mavutil

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(HOME[0]))
WORK = os.path.expanduser('~/cg-terrain-fs-midflight')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
SPEEDUP = 8
TYPE_MASK_POSITION_ONLY = 0b0000111111111000


def at(north, east):
    return HOME[0] + north / M_LAT, HOME[1] + east / M_LON


def start(wipe):
    return subprocess.Popen([BIN] + (['-w'] if wipe else []) + ['--model', '+', '-I', '0', '-s', str(SPEEDUP), '--home', '%s,%s,%s,0' % HOME],
                            cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arducopter'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(os.path.join(WORK, 'terrain'))
    src = os.path.join(TREE, 'terrain', 'S36E149.DAT')
    if os.path.isfile(src) and os.path.getsize(src) > 0:
        shutil.copy(src, os.path.join(WORK, 'terrain', 'S36E149.DAT'))
    # S36E148.DAT (the tile 19 km west) deliberately not copied: a fresh, genuinely empty file gets created there on first access, the same shape as a real SRTM void.
    notes, track, proc = [], [], start(True)
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 33, 200000, 0, 0, 0, 0, 0)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 136, 200000, 0, 0, 0, 0, 0)
        time.sleep(45)
        base = link.read_params(conn)
        bad = [r.name for r in params.write(conn, [params.Change('TERRAIN_ENABLE', base.get('TERRAIN_ENABLE'), 1.0)]) if not r.ok]
        notes.append('TERRAIN_ENABLE -> 1 (rejected %s); restarting' % bad)
        time.sleep(2)
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
        proc = start(False)
        conn, _ = link.connect(5760, timeout=120.0)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 33, 200000, 0, 0, 0, 0, 0)
        ack_a = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 136, 200000, 0, 0, 0, 0, 0)
        ack_b = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
        notes.append('stream requests after reboot: GLOBAL_POSITION_INT ack %s, TERRAIN_REPORT ack %s' % (None if ack_a is None else ack_a.result, None if ack_b is None else ack_b.result))
        time.sleep(40)
        after = link.read_params(conn)
        notes.append('after restart: TERRAIN_ENABLE=%s' % after.get('TERRAIN_ENABLE'))
        flight.set_mode(conn, 'GUIDED', table='copter')
        armed = flight.arm(conn, timeout=150.0)
        notes.append('arm (no mission uploaded, so no terrain pre-arm gate): %s' % armed.detail)
        for text in armed.texts:
            notes.append('  text: %s' % text)
        if not armed.ok:
            notes.append('not armed, nothing further to do')
        else:
            conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, 40.0)  # MAV_CMD_NAV_TAKEOFF, alt 40 m
            ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
            notes.append('takeoff ack %s' % (None if ack is None else ack.result))
            time.sleep(20)
            wp = at(0, -19000)  # 19 km west: past the S36E149/S36E148 boundary at lon 149.0 (home lon 149.165230), well inside the empty neighbour tile
            conn.mav.set_position_target_global_int_send(0, conn.target_system, conn.target_component, mavutil.mavlink.MAV_FRAME_GLOBAL_TERRAIN_ALT_INT, TYPE_MASK_POSITION_ONLY,
                                                          int(wp[0] * 1e7), int(wp[1] * 1e7), 40.0, 0, 0, 0, 0, 0, 0, 0, 0)
            notes.append('SET_POSITION_TARGET_GLOBAL_INT (terrain-alt) sent: lat=%.7f lon=%.7f alt=40.0, 19 km west of home into the empty tile' % wp)
            begin, last_mode = time.time(), None
            while time.time() - begin < 600.0:
                msg = conn.recv_match(type=['HEARTBEAT', 'STATUSTEXT', 'TERRAIN_REPORT'], blocking=True, timeout=1)
                t = time.time() - begin
                if msg is None:
                    continue
                kind = msg.get_type()
                if kind == 'STATUSTEXT':
                    notes.append('t=%6.1f vehicle: %s' % (t, msg.text))
                elif kind == 'TERRAIN_REPORT':
                    track.append([round(t, 1), 'TERRAIN_REPORT', msg.loaded, msg.pending, msg.terrain_height, msg.current_height])
                elif msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                    mode = flight.mode_name(msg.custom_mode, 'copter')
                    track.append([round(t, 1), 'HEARTBEAT', mode, flight.is_armed(msg), '', ''])
                    if mode != last_mode:
                        notes.append('t=%6.1f mode %s' % (t, mode))
                        last_mode = mode
                        if mode == 'RTL':
                            notes.append('t=%6.1f reached RTL, stopping the hold early' % t)
                            time.sleep(10)
                            break
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    with open(os.path.join(OUT, 'terrain-failsafe-midflight-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    with open(os.path.join(OUT, 'terrain-failsafe-midflight-track.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['seconds', 'kind', 'a', 'b', 'c', 'd'])
        w.writerows(track)
    print('[terrain-failsafe-midflight] %d notes, %d track rows' % (len(notes), len(track)), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
