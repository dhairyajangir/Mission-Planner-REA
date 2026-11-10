"""Terrain-relative waypoints (AP_Terrain), not tested anywhere else in this repository: a mission with MAV_FRAME_GLOBAL_TERRAIN_ALT waypoints several km from home, where the ground
elevation genuinely changes, to see whether the vehicle holds a constant height above the terrain (not above home or sea level). Real elevation data for this project's home location
exists in the pinned snapshot's own tree (`terrain/S36E149.DAT`, 2.1 MB; `terrain/S36E148.DAT` is present but empty, 0 bytes, and not needed for this route). Simulator only
(WSL, pymavlink, the custom-gcs library).

    python3 sitl-terrain-following.py <ardupilot tree> <out dir> <custom-gcs dir> [vehicle ...]      vehicles: plane, copter

TERRAIN_ENABLE is an enable-flag parameter (needs a reboot, the same two-stage pattern as SERVO_DSHOT_ESC/SOAR_ENABLE/AROT_ENABLE/BATT_MONITOR elsewhere in this repository): a first
start copies the tree's terrain tiles into the simulator's own `terrain/` folder and sets TERRAIN_ENABLE 1, the second start (no wipe) keeps it. The mission: a normal takeoff, then two
MAV_FRAME_GLOBAL_TERRAIN_ALT waypoints about 5 and 3 km from home (the same two points ArduPilot's own ArduPlane_Tests/TerrainMission/ap-terrain.txt uses, where the ground rises inland),
both commanding 100 m above the terrain, then a return. TERRAIN_REPORT (current height above terrain, terrain height AMSL) and GLOBAL_POSITION_INT (height above home) are logged
together; if terrain following works, the height-above-terrain should stay near 100 m while the height-above-home varies as the ground rises and falls.
"""
import csv
import math
import os
import shutil
import subprocess
import sys
import time

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
WANT = sys.argv[4:] or ['plane', 'copter']
sys.path.insert(0, GCS)
from customgcs import flight, link, mission, params  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(HOME[0]))
WORK = os.path.expanduser('~/cg-terrain')
VEH = {'plane': ('arduplane', 'plane', 'plane'), 'copter': ('arducopter', '+', 'copter')}
# the two terrain-relative points from ArduPlane_Tests/TerrainMission/ap-terrain.txt, where the ground is known to change
WP2, WP3 = (-35.361821, 149.112238), (-35.367368, 149.156778)


def terrain_item(seq, lat, lon, alt_agl):
    return mission.Item(seq, 10, 16, 0, 1, 0, 0, 0, 0, lat, lon, alt_agl)       # frame 10 = MAV_FRAME_GLOBAL_TERRAIN_ALT


def route(table):
    items = [mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2])]
    if table == 'plane':
        items.append(mission.Item(1, 3, 22, 1, 1, 15.0, 0, 0, 0, 0.0, 0.0, 80.0))
    else:
        items.append(mission.Item(1, 3, 22, 1, 1, 0, 0, 0, 0, 0.0, 0.0, 80.0))
    items.append(terrain_item(2, WP2[0], WP2[1], 100.0))
    items.append(terrain_item(3, WP3[0], WP3[1], 100.0))
    items.append(mission.Item(4, 3, (21 if table == 'plane' else 20), 0, 1, 0, 0, 0, 0, 0.0, 0.0, 0.0))
    return items


def start(binary, model, wipe):
    return subprocess.Popen([os.path.join(TREE, 'build/sitl/bin', binary)] + (['-w'] if wipe else []) + ['--model', model, '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME],
                            cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)


def fly(name):
    binary, model, table = VEH[name]
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(os.path.join(WORK, 'terrain'))
    for f in ('S36E149.DAT', 'S36E148.DAT'):
        src = os.path.join(TREE, 'terrain', f)
        if os.path.isfile(src) and os.path.getsize(src) > 0:
            shutil.copy(src, os.path.join(WORK, 'terrain', f))
    notes, rows, proc = [], [], start(binary, model, True)
    try:
        conn, _ = link.connect(5760, timeout=120.0)
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
        proc = start(binary, model, False)
        conn, _ = link.connect(5760, timeout=120.0)
        time.sleep(45)
        after = link.read_params(conn)
        notes.append('after restart TERRAIN_ENABLE=%s' % after.get('TERRAIN_ENABLE'))
        notes.append('upload ack %s' % mission.upload(conn, route(table)))
        flight.set_mode(conn, 'MANUAL' if table == 'plane' else 'STABILIZE', table=table)
        armed = flight.arm(conn, timeout=150.0)
        notes.append('arm: %s' % armed.detail)
        if armed.ok:
            auto = flight.set_mode(conn, 'AUTO', table=table)
            give_up = time.time() + 90.0
            while not auto.ok and time.time() < give_up:
                time.sleep(3)
                auto = flight.set_mode(conn, 'AUTO', table=table)
            notes.append('AUTO: %s' % auto.detail)
            if table == 'copter':
                notes.append('start: %s' % flight.start_mission(conn).detail)
            begin, last_report, was = time.time(), None, False
            while time.time() - begin < 600.0:
                msg = conn.recv_match(type=['HEARTBEAT', 'STATUSTEXT', 'TERRAIN_REPORT', 'GLOBAL_POSITION_INT'], blocking=True, timeout=1)
                if msg is None:
                    continue
                t = time.time() - begin
                kind = msg.get_type()
                if kind == 'STATUSTEXT':
                    notes.append('t=%6.1f vehicle: %s' % (t, msg.text))
                elif kind == 'TERRAIN_REPORT':
                    last_report = (round(msg.current_height, 1), round(msg.terrain_height, 1))
                elif kind == 'GLOBAL_POSITION_INT':
                    rows.append([round(t, 1), msg.lat / 1e7, msg.lon / 1e7, msg.relative_alt / 1000.0, last_report[0] if last_report else '', last_report[1] if last_report else ''])
                elif msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                    now = flight.is_armed(msg)
                    if was and not now:
                        notes.append('t=%6.1f disarmed' % t)
                        break
                    was = was or now
        else:
            notes.extend('vehicle: ' + t for t in armed.texts)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
        try:
            proc.wait(15)
        except Exception:
            proc.kill()
    with open(os.path.join(OUT, name + '-terrain-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    with open(os.path.join(OUT, name + '-terrain-track.csv'), 'w', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['seconds', 'lat', 'lon', 'relative_alt_home_m', 'height_above_terrain_m', 'terrain_height_amsl_m'])
        w.writerows(rows)
    heights = [r[4] for r in rows if r[4] != '']
    print('[%s] %d TERRAIN_REPORT samples; height above terrain min/max %s/%s; %s' % (name, len(heights), min(heights) if heights else None, max(heights) if heights else None,
                                                                                      notes[-1] if notes else ''), flush=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    for name in WANT:
        fly(name)
    return 0


if __name__ == '__main__':
    sys.exit(main())
