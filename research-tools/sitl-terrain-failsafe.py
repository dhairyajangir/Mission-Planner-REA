"""Fault injection the earlier terrain-following test named as untested ("no terrain data gaps, holes or SRTM voids were tested", ArduPilot-Aerial-Library-Execution-Trace.md):
a Copter mission with a MAV_FRAME_GLOBAL_TERRAIN_ALT waypoint over a location this simulator has no cached tile for at all (the simulator's terrain/ folder starts empty; the pinned
snapshot's only tile, S36E149.DAT, is never copied in). ArduCopter has a dedicated terrain failsafe for exactly this (ArduCopter/events.cpp: failsafe_terrain_check/_on_event,
ArduCopter/config.h FS_TERRAIN_TIMEOUT_MS 5000): after 5 s of missing terrain data in a mode that requires it, it logs an error, sends "Failsafe: Terrain data missing" and (per
should_disarm_on_failsafe) either RTLs or disarms. TERRAIN_REPORT's own `loaded` field (tiles loaded for the current location) should read 0 throughout, since nothing was ever
cached and SITL has no real tile server to satisfy a pending request. Simulator only (WSL, pymavlink, the custom-gcs library).

    python3 sitl-terrain-failsafe.py <ardupilot tree> <out dir> <custom-gcs dir>
"""
import csv
import math
import os
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, GCS)
from customgcs import flight, link, mission, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(HOME[0]))
WORK = os.path.expanduser('~/cg-terrain-fs')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')


def at(north, east):
    return HOME[0] + north / M_LAT, HOME[1] + east / M_LON


def route():
    wp = at(400, 0)
    items = [mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2]), mission.Item(1, 3, 22, 1, 1, 0, 0, 0, 0, 0.0, 0.0, 30.0),
             mission.Item(2, 10, 16, 0, 1, 0, 0, 0, 0, wp[0], wp[1], 40.0),  # frame 10 = MAV_FRAME_GLOBAL_TERRAIN_ALT, no tile cached here at all
             mission.Item(3, 3, 20, 0, 1, 0, 0, 0, 0, 0.0, 0.0, 0.0)]  # RTL
    return items


def start(wipe):
    return subprocess.Popen([BIN] + (['-w'] if wipe else []) + ['--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME],
                            cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arducopter'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)  # deliberately no terrain/ tiles copied in: every location this run asks about has no cached data
    notes, track, proc = [], [], start(True)
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 33, 200000, 0, 0, 0, 0, 0)   # GLOBAL_POSITION_INT at 5 Hz (Copter does not stream it unasked)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 136, 200000, 0, 0, 0, 0, 0)  # TERRAIN_REPORT at 5 Hz (Copter does not stream this either)
        time.sleep(45)
        base = link.read_params(conn)
        bad = [r.name for r in params.write(conn, [params.Change('TERRAIN_ENABLE', base.get('TERRAIN_ENABLE'), 1.0)]) if not r.ok]
        notes.append('TERRAIN_ENABLE was %s, set to 1 (rejected %s); restarting' % (base.get('TERRAIN_ENABLE'), bad))
        time.sleep(2)
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
        proc = start(False)
        conn, _ = link.connect(5760, timeout=120.0)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 33, 200000, 0, 0, 0, 0, 0)   # stream requests do not survive the reboot
        ack_a = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 136, 200000, 0, 0, 0, 0, 0)
        ack_b = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
        notes.append('stream requests after reboot: GLOBAL_POSITION_INT ack %s, TERRAIN_REPORT ack %s' % (None if ack_a is None else ack_a.result, None if ack_b is None else ack_b.result))
        time.sleep(40)
        notes.append('upload ack %s' % mission.upload(conn, route()))
        flight.set_mode(conn, 'STABILIZE', table='copter')
        armed = flight.arm(conn, timeout=150.0)
        notes.append('arm: %s' % armed.detail)
        for text in armed.texts:
            notes.append('  prearm text: %s' % text)
        if armed.ok:
            auto = flight.set_mode(conn, 'AUTO', table='copter')
            notes.append('AUTO: %s' % auto.detail)
            begin, last_mode = time.time(), None
            while time.time() - begin < 90.0:
                msg = conn.recv_match(type=['HEARTBEAT', 'STATUSTEXT', 'TERRAIN_REPORT'], blocking=True, timeout=1)
                t = time.time() - begin
                if msg is None:
                    continue
                kind = msg.get_type()
                if kind == 'STATUSTEXT':
                    notes.append('t=%5.1f vehicle: %s' % (t, msg.text))
                elif kind == 'TERRAIN_REPORT':
                    track.append([round(t, 1), 'TERRAIN_REPORT', msg.loaded, msg.pending, msg.terrain_height, msg.current_height])
                elif msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                    mode = flight.mode_name(msg.custom_mode, 'copter')
                    if mode != last_mode:
                        notes.append('t=%5.1f mode %s' % (t, mode))
                        last_mode = mode
                    track.append([round(t, 1), 'HEARTBEAT', mode, flight.is_armed(msg), '', ''])
        else:
            notes.append('not armed, mission not started')
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    with open(os.path.join(OUT, 'terrain-failsafe-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    with open(os.path.join(OUT, 'terrain-failsafe-track.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['seconds', 'kind', 'a', 'b', 'c', 'd'])
        w.writerows(track)
    print('[terrain-failsafe] %d notes, %d track rows' % (len(notes), len(track)), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
