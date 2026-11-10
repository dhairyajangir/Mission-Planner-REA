"""What does each aerial autopilot send over MAVLink, and how often? A census of the messages a ground station receives from the Copter, Plane, QuadPlane and helicopter builds in a simulator,
with no stream requests (the default SRn_ stream rates), on the ground (disarmed) and in flight. Simulator only (WSL, pymavlink, the custom-gcs library).

    python3 sitl-mavlink-census.py <ardupilot tree> <out dir> <custom-gcs dir> [vehicle ...]       vehicles: copter, plane, quadplane, heli

Per vehicle: a fresh simulator, 45 s of start-up, 60 s counted on the ground, then a mission flight (copter: takeoff to 15 m and a loiter; plane: automatic takeoff to 60 m and waypoints; quadplane:
VTOL takeoff to 30 m and a waypoint; heli: interlock switch by RC override, takeoff to 20 m and a loiter) and 30 s counted 40 s after the mission started. Messages are counted by name and
source component; the output CSV has count and rate per phase. The GCS heartbeat is not sent, so the vehicle sees no ground station, as in a bare connection.
"""
import csv
import math
import os
import subprocess
import sys
import threading
import time
from collections import Counter

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
WANT = sys.argv[4:] or ['copter', 'plane', 'quadplane', 'heli']
sys.path.insert(0, GCS)
from customgcs import flight, link, mission  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(35.363261))
WORK = os.path.expanduser('~/cg-census')
VEH = {
    'copter': ('arducopter', '+', 'copter'), 'plane': ('arduplane', 'plane', 'plane'), 'quadplane': ('arduplane', 'quadplane', 'plane'), 'heli': ('arducopter-heli', 'heli', 'copter'),
}


def at(north, east):
    return HOME[0] + north / M_LAT, HOME[1] + east / M_LON


def item(seq, command, point=(0.0, 0.0), alt=0.0, p1=0.0, param=0.0):
    return mission.Item(seq, 3, command, 1 if seq == 1 else 0, 1, p1, 0, 0, 0, point[0], point[1], alt)


def home_item():
    return mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2])


MISSIONS = {
    'copter': [home_item(), item(1, 22, alt=15.0), item(2, 19, at(40, 0), 15.0, p1=300.0)],
    'plane': [home_item(), item(1, 22, alt=60.0, p1=15.0), item(2, 16, at(300, 0), 60.0), item(3, 16, at(300, 300), 60.0), item(4, 16, at(0, 300), 60.0)],
    'quadplane': [home_item(), item(1, 84, alt=30.0), item(2, 16, at(250, 0), 60.0), item(3, 16, at(250, 250), 60.0)],
    'heli': [home_item(), item(1, 22, alt=20.0), item(2, 19, at(40, 0), 20.0, p1=300.0)],
}


class Sticks(threading.Thread):
    def __init__(self, conn):
        super().__init__(daemon=True)
        self.conn, self.collective, self.interlock, self.running = conn, 1000, 1000, True

    def run(self):
        while self.running:
            try:
                self.conn.mav.rc_channels_override_send(self.conn.target_system, self.conn.target_component, 1500, 1500, self.collective, 1500, 0, 0, 0, self.interlock)
            except Exception:
                pass
            time.sleep(0.1)


def count(conn, seconds):
    c, end = Counter(), time.time() + seconds
    while time.time() < end:
        msg = conn.recv_match(blocking=True, timeout=1)
        if msg is None:
            continue
        t = msg.get_type()
        if t == 'BAD_DATA':
            continue
        c[(t, msg.get_srcComponent())] += 1
    return c, seconds


def census(name):
    binary, model, table = VEH[name]
    subprocess.call(['pkill', '-x', binary])
    time.sleep(1)
    work = os.path.join(WORK, name)
    subprocess.call(['rm', '-rf', work])
    os.makedirs(work)
    proc = subprocess.Popen([os.path.join(TREE, 'build/sitl/bin', binary), '-w', '--model', model, '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=work,
                            stdout=open(os.path.join(work, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    notes, ground, air, sticks = [], None, None, None
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        time.sleep(45)
        ground = count(conn, 60.0)
        notes.append('upload ack %s' % mission.upload(conn, MISSIONS[name]))
        if name == 'heli':
            sticks = Sticks(conn)
            sticks.start()
        flight.set_mode(conn, 'MANUAL' if table == 'plane' else 'STABILIZE', table=table)
        armed = flight.arm(conn, timeout=150.0)
        notes.append('arm: %s' % armed.detail)
        if armed.ok:
            if sticks:
                sticks.interlock = 2000
                time.sleep(25)
                sticks.collective = 1500
            auto = flight.set_mode(conn, 'AUTO', table=table)
            give_up = time.time() + 90.0
            while not auto.ok and time.time() < give_up:
                time.sleep(3)
                auto = flight.set_mode(conn, 'AUTO', table=table)
            notes.append('AUTO: %s' % auto.detail)
            if table == 'copter':
                notes.append('start: %s' % flight.start_mission(conn).detail)
            time.sleep(40)
            air = count(conn, 30.0)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        if sticks:
            sticks.running = False
        subprocess.call(['pkill', '-x', binary])
        try:
            proc.wait(15)
        except Exception:
            proc.kill()
    return ground, air, notes


def main():
    os.makedirs(OUT, exist_ok=True)
    rows, allnotes = [], {}
    for name in WANT:
        ground, air, notes = census(name)
        allnotes[name] = notes
        keys = set()
        for phase in (ground, air):
            if phase:
                keys |= set(phase[0])
        for key in sorted(keys):
            g = ground[0][key] if ground else 0
            a = air[0][key] if air else 0
            rows.append([name, key[0], key[1], g, round(g / ground[1], 3) if ground else '', a, round(a / air[1], 3) if air else ''])
        print('[%s] %d message types; %s' % (name, len({k[0] for k in keys}), notes[:2]), flush=True)
    with open(os.path.join(OUT, 'mavlink-census.csv'), 'w', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['vehicle', 'message', 'source_component', 'ground_count_60s', 'ground_hz', 'flight_count_30s', 'flight_hz'])
        w.writerows(rows)
    with open(os.path.join(OUT, 'mavlink-census-notes.txt'), 'w') as f:
        for k, v in allnotes.items():
            f.write('%s: %s\n' % (k, '; '.join(v)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
