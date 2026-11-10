"""GUIDED-mode offboard control: SET_POSITION_TARGET_LOCAL_NED on Copter (position and velocity-only), SET_POSITION_TARGET_GLOBAL_INT on Plane. This is the message pair a companion
computer or custom ground station uses for direct control, distinct from an uploaded AUTO mission or an immediate MAV_CMD; neither vehicle's handling of it was tested elsewhere in this
repository. Simulator only (WSL, pymavlink, the custom-gcs library).

    python3 sitl-guided-offboard-control.py <ardupilot tree> <out dir> <custom-gcs dir> [part ...]      parts: copter-position, copter-velocity, plane-position, plane-reposition

copter-position   GUIDED takeoff to 15 m (MAV_CMD_NAV_TAKEOFF via COMMAND_LONG, the usual way into GUIDED flight), then one SET_POSITION_TARGET_LOCAL_NED with a position-only type_mask
                  (ignore velocity/acceleration/yaw), target 20 m north, 10 m east, 5 m above the takeoff height (NED: positive z is down, so z = -5). The vehicle's track is logged for
                  30 s and the final position compared with the target.
copter-velocity   the same takeoff, then a velocity-only type_mask, target 2 m/s north, sent every 0.5 s for 10 s (as a companion computer would stream it, since ArduCopter's GUIDED
                  velocity controller times out without repeated messages), then zero velocity to stop. The track and the speed reached are logged.
plane-position    GUIDED mode on an already-flying Plane (the mission from sitl-plane-gaps.py's plane flight, switched to GUIDED after the second waypoint), then one
                  SET_POSITION_TARGET_GLOBAL_INT with a position-only type_mask aimed at a point 400 m further on at 80 m. The vehicle's track and the distance to that target are logged.

Both message types fill many fields; a position-only or velocity-only type_mask bit pattern is used throughout (GUIDED commonly needs exactly one at a time, not a mix), and the
unused fields are sent as zero. No parameters are changed; nothing beyond this one MAVLink message pair is tested (no GUIDED_CHANGE_* commands, no yaw control, no acceleration terms).
"""
import csv
import math
import os
import subprocess
import sys
import time

from pymavlink import mavutil

TREE, OUT, GCS = sys.argv[1], sys.argv[2], sys.argv[3]
PARTS = sys.argv[4:] or ['copter-position', 'copter-velocity', 'plane-position']
sys.path.insert(0, GCS)
from customgcs import flight, link, mission  # noqa: E402

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(35.363261))
WORK = os.path.expanduser('~/cg-offboard')
TYPE_MASK_POSITION_ONLY = 0b0000111111111000     # ignore velocity, acceleration and yaw/yaw-rate (bits 3-10); position (x,y,z) and the frame's own meaning are used
TYPE_MASK_VELOCITY_ONLY = 0b0000111111000111     # ignore position, acceleration and yaw/yaw-rate; velocity (vx,vy,vz) used


def at(north, east):
    return HOME[0] + north / M_LAT, HOME[1] + east / M_LON


def start_copter():
    proc = subprocess.Popen([os.path.join(TREE, 'build/sitl/bin/arducopter'), '-w', '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                            stdout=open(os.path.join(WORK, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    return proc


def start_plane():
    proc = subprocess.Popen([os.path.join(TREE, 'build/sitl/bin/arduplane'), '-w', '--model', 'plane', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME], cwd=WORK,
                            stdout=open(os.path.join(WORK, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    return proc


def fresh():
    subprocess.call(['pkill', '-f', 'build/sitl/bin/ardu'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)


def stop(proc, binary):
    subprocess.call(['pkill', '-x', binary])
    try:
        proc.wait(15)
    except Exception:
        proc.kill()


def track_row(conn, t0):
    msg = conn.recv_match(type=['GLOBAL_POSITION_INT'], blocking=True, timeout=1)
    if msg is None:
        return None
    return [round(time.time() - t0, 1), msg.lat / 1e7, msg.lon / 1e7, msg.relative_alt / 1000.0, msg.vx / 100.0, msg.vy / 100.0]


def write_track(name, rows):
    with open(os.path.join(OUT, name + '-track.csv'), 'w', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['seconds', 'lat', 'lon', 'relative_alt_m', 'vx_ms', 'vy_ms'])
        w.writerows(rows)


def copter_position():
    fresh()
    notes, proc = [], start_copter()
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 33, 200000, 0, 0, 0, 0, 0)  # SET_MESSAGE_INTERVAL: GLOBAL_POSITION_INT at 5 Hz (Copter does not stream it unasked)
        time.sleep(45)
        flight.set_mode(conn, 'GUIDED')
        armed = flight.arm(conn, timeout=120.0)
        notes.append('arm: %s' % armed.detail)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, 15.0)  # MAV_CMD_NAV_TAKEOFF, alt 15 m
        ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
        notes.append('takeoff ack %s' % (None if ack is None else ack.result))
        time.sleep(15)
        target_north, target_east, target_alt = 20.0, 10.0, 20.0           # 5 m above the 15 m takeoff
        conn.mav.set_position_target_local_ned_send(0, conn.target_system, conn.target_component, mavutil.mavlink.MAV_FRAME_LOCAL_NED, TYPE_MASK_POSITION_ONLY,
                                                     target_north, target_east, -target_alt, 0, 0, 0, 0, 0, 0, 0, 0)
        notes.append('SET_POSITION_TARGET_LOCAL_NED sent: north=%.1f east=%.1f alt=%.1f (NED x,y,z)' % (target_north, target_east, target_alt))
        t0, rows = time.time(), []
        while time.time() - t0 < 30.0:
            r = track_row(conn, t0)
            if r:
                rows.append(r)
        last = rows[-1] if rows else None
        if last:
            d_north = (last[1] - HOME[0]) * M_LAT
            d_east = (last[2] - HOME[1]) * M_LON
            notes.append('after 30 s: %.1f m north, %.1f m east, %.1f m alt (target %.1f, %.1f, %.1f)' % (d_north, d_east, last[3], target_north, target_east, target_alt))
        write_track('copter-position', rows)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        stop(proc, 'arducopter')
    with open(os.path.join(OUT, 'copter-position-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    print('[copter-position] %s' % notes[-1] if notes else '[copter-position] no notes', flush=True)


def copter_velocity():
    fresh()
    notes, proc = [], start_copter()
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 33, 200000, 0, 0, 0, 0, 0)  # SET_MESSAGE_INTERVAL: GLOBAL_POSITION_INT at 5 Hz (Copter does not stream it unasked)
        time.sleep(45)
        flight.set_mode(conn, 'GUIDED')
        armed = flight.arm(conn, timeout=120.0)
        notes.append('arm: %s' % armed.detail)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, 15.0)
        ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
        notes.append('takeoff ack %s' % (None if ack is None else ack.result))
        time.sleep(15)
        t0, rows, last_send = time.time(), [], 0.0
        while time.time() - t0 < 10.0:
            if time.time() - t0 - last_send >= 0.5:
                conn.mav.set_position_target_local_ned_send(0, conn.target_system, conn.target_component, mavutil.mavlink.MAV_FRAME_LOCAL_NED, TYPE_MASK_VELOCITY_ONLY,
                                                             0, 0, 0, 2.0, 0, 0, 0, 0, 0, 0, 0)   # 2 m/s north
                last_send = time.time() - t0
            r = track_row(conn, t0)
            if r:
                rows.append(r)
        max_speed = max((r[4] for r in rows), default=0.0)
        notes.append('streamed vx=2.0 m/s north for 10 s; max measured vx %.2f m/s' % max_speed)
        conn.mav.set_position_target_local_ned_send(0, conn.target_system, conn.target_component, mavutil.mavlink.MAV_FRAME_LOCAL_NED, TYPE_MASK_VELOCITY_ONLY, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        notes.append('sent zero velocity to stop')
        t1 = time.time()
        while time.time() - t1 < 10.0:
            r = track_row(conn, t0)
            if r:
                rows.append(r)
        notes.append(('10 s after stopping: vx %.2f m/s (no further velocity messages sent)' % rows[-1][4]) if rows else 'no rows')
        write_track('copter-velocity', rows)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        stop(proc, 'arducopter')
    with open(os.path.join(OUT, 'copter-velocity-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    print('[copter-velocity] %s' % notes[-1] if notes else '[copter-velocity] no notes', flush=True)


def plane_position():
    fresh()
    notes, proc = [], start_plane()
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        time.sleep(45)
        a, b = at(300, 0), at(300, 300)
        items = [mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2]), mission.Item(1, 3, 22, 1, 1, 15.0, 0, 0, 0, 0.0, 0.0, 60.0),
                 mission.Item(2, 3, 16, 0, 1, 0, 0, 0, 0, a[0], a[1], 60.0), mission.Item(3, 3, 16, 0, 1, 0, 0, 0, 0, b[0], b[1], 60.0)]
        notes.append('upload ack %s' % mission.upload(conn, items))
        flight.set_mode(conn, 'MANUAL', table='plane')
        armed = flight.arm(conn, timeout=150.0)
        notes.append('arm: %s' % armed.detail)
        auto = flight.set_mode(conn, 'AUTO', table='plane')
        give_up = time.time() + 90.0
        while not auto.ok and time.time() < give_up:
            time.sleep(3)
            auto = flight.set_mode(conn, 'AUTO', table='plane')
        notes.append('AUTO: %s' % auto.detail)
        time.sleep(30)                                                        # let it take off and reach the first waypoint area
        guided = flight.set_mode(conn, 'GUIDED', table='plane')
        notes.append('GUIDED: %s' % guided.detail)
        target_lat, target_lon, target_alt = at(700, 300)[0], at(700, 300)[1], 80.0
        conn.mav.set_position_target_global_int_send(0, conn.target_system, conn.target_component, mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT, TYPE_MASK_POSITION_ONLY,
                                                      int(target_lat * 1e7), int(target_lon * 1e7), target_alt, 0, 0, 0, 0, 0, 0, 0, 0)
        notes.append('SET_POSITION_TARGET_GLOBAL_INT sent: lat=%.7f lon=%.7f alt=%.1f' % (target_lat, target_lon, target_alt))
        t0, rows = time.time(), []
        while time.time() - t0 < 60.0:
            r = track_row(conn, t0)
            if r:
                rows.append(r)
        last = rows[-1] if rows else None
        if last:
            dist = math.hypot((last[1] - target_lat) * M_LAT, (last[2] - target_lon) * M_LON)
            notes.append('after 60 s: %.1f m from the GUIDED target, alt %.1f m' % (dist, last[3]))
        write_track('plane-position', rows)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        stop(proc, 'arduplane')
    with open(os.path.join(OUT, 'plane-position-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    print('[plane-position] %s' % notes[-1] if notes else '[plane-position] no notes', flush=True)


def plane_reposition():
    """MAV_CMD_DO_REPOSITION (number 192), the command whose handler (handle_command_int_DO_REPOSITION) does decode and use the target lat/lon, unlike SET_POSITION_TARGET_GLOBAL_INT
    (see plane_position() above). Same flight and same target as plane_position(), for a direct comparison."""
    fresh()
    notes, proc = [], start_plane()
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        time.sleep(45)
        a, b = at(300, 0), at(300, 300)
        items = [mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2]), mission.Item(1, 3, 22, 1, 1, 15.0, 0, 0, 0, 0.0, 0.0, 60.0),
                 mission.Item(2, 3, 16, 0, 1, 0, 0, 0, 0, a[0], a[1], 60.0), mission.Item(3, 3, 16, 0, 1, 0, 0, 0, 0, b[0], b[1], 60.0)]
        notes.append('upload ack %s' % mission.upload(conn, items))
        flight.set_mode(conn, 'MANUAL', table='plane')
        armed = flight.arm(conn, timeout=150.0)
        notes.append('arm: %s' % armed.detail)
        auto = flight.set_mode(conn, 'AUTO', table='plane')
        give_up = time.time() + 90.0
        while not auto.ok and time.time() < give_up:
            time.sleep(3)
            auto = flight.set_mode(conn, 'AUTO', table='plane')
        notes.append('AUTO: %s' % auto.detail)
        time.sleep(30)
        target_lat, target_lon, target_alt = at(700, 300)[0], at(700, 300)[1], 80.0
        conn.mav.command_int_send(conn.target_system, conn.target_component, mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT, 192, 0, 0, 0, 1, 0, 0, int(target_lat * 1e7), int(target_lon * 1e7), target_alt)  # param2=1: MAV_DO_REPOSITION_FLAGS_CHANGE_MODE (the plane is still in AUTO, not GUIDED)
        ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
        notes.append('DO_REPOSITION sent: lat=%.7f lon=%.7f alt=%.1f; ack %s' % (target_lat, target_lon, target_alt, None if ack is None else ack.result))
        t0, rows = time.time(), []
        while time.time() - t0 < 60.0:
            r = track_row(conn, t0)
            if r:
                rows.append(r)
        last = rows[-1] if rows else None
        if last:
            dist = math.hypot((last[1] - target_lat) * M_LAT, (last[2] - target_lon) * M_LON)
            notes.append('after 60 s: %.1f m from the target, alt %.1f m' % (dist, last[3]))
        write_track('plane-reposition', rows)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        stop(proc, 'arduplane')
    with open(os.path.join(OUT, 'plane-reposition-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    print('[plane-reposition] %s' % (notes[-1] if notes else 'no notes'), flush=True)


def plane_guided_slew():
    """The GUIDED-only 'slew' commands (AP_PLANE_OFFBOARD_GUIDED_SLEW_ENABLED, handle_command_int_guided_slew_commands): GUIDED_CHANGE_SPEED (43000), GUIDED_CHANGE_ALTITUDE (43001) and
    GUIDED_CHANGE_HEADING (43002). All three return FAILED unless the vehicle is already in GUIDED mode (confirmed in the disarmed command sweep, where all three failed) and the full
    command sweep never tried them with the vehicle actually in GUIDED and flying. Reaches GUIDED the same way plane_reposition() does, then sends all three, 20 s apart, holding the
    last for 40 s."""
    fresh()
    notes, proc = [], start_plane()
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        time.sleep(45)
        a, b = at(300, 0), at(300, 300)
        items = [mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2]), mission.Item(1, 3, 22, 1, 1, 15.0, 0, 0, 0, 0.0, 0.0, 60.0),
                 mission.Item(2, 3, 16, 0, 1, 0, 0, 0, 0, a[0], a[1], 60.0), mission.Item(3, 3, 16, 0, 1, 0, 0, 0, 0, b[0], b[1], 60.0)]
        notes.append('upload ack %s' % mission.upload(conn, items))
        flight.set_mode(conn, 'MANUAL', table='plane')
        armed = flight.arm(conn, timeout=150.0)
        notes.append('arm: %s' % armed.detail)
        auto = flight.set_mode(conn, 'AUTO', table='plane')
        give_up = time.time() + 90.0
        while not auto.ok and time.time() < give_up:
            time.sleep(3)
            auto = flight.set_mode(conn, 'AUTO', table='plane')
        notes.append('AUTO: %s' % auto.detail)
        time.sleep(30)
        target_lat, target_lon, target_alt = at(700, 300)[0], at(700, 300)[1], 80.0
        conn.mav.command_int_send(conn.target_system, conn.target_component, mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT, 192, 0, 0, 0, 1, 0, 0,
                                  int(target_lat * 1e7), int(target_lon * 1e7), target_alt)
        ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
        notes.append('DO_REPOSITION to reach GUIDED: ack %s' % (None if ack is None else ack.result))
        t0, rows = time.time(), []

        def hold(seconds):
            end = time.time() + seconds
            while time.time() < end:
                r = track_row(conn, t0)
                if r:
                    rows.append(r)

        hold(15.0)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 43000, 0, 0, 30.0, 2.0, 0, 0, 0, 0)  # GUIDED_CHANGE_SPEED: type=0 airspeed, target 30 m/s, accel 2 m/s^2
        ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
        notes.append('t=%5.1f GUIDED_CHANGE_SPEED to 30 m/s airspeed: ack %s' % (time.time() - t0, None if ack is None else ack.result))
        hold(20.0)
        conn.mav.command_int_send(conn.target_system, conn.target_component, mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT, 43001, 0, 0, 0, 0, 3.0, 0, 0, 0, 120.0)  # GUIDED_CHANGE_ALTITUDE: 120 m, rate 3 m/s
        ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
        notes.append('t=%5.1f GUIDED_CHANGE_ALTITUDE to 120 m: ack %s' % (time.time() - t0, None if ack is None else ack.result))
        hold(20.0)
        conn.mav.command_long_send(conn.target_system, conn.target_component, 43002, 0, 1, 270.0, 0, 0, 0, 0, 0)  # GUIDED_CHANGE_HEADING: type=1 raw heading, 270 degrees
        ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
        notes.append('t=%5.1f GUIDED_CHANGE_HEADING to 270 deg: ack %s' % (time.time() - t0, None if ack is None else ack.result))
        hold(40.0)
        last = rows[-1] if rows else None
        if last:
            notes.append('final: alt %.1f m, vx %.2f vy %.2f (heading atan2(vy,vx), degrees from north clockwise = %.0f)' % (last[3], last[4], last[5], (math.degrees(math.atan2(last[5], last[4])) % 360)))
        write_track('plane-guided-slew', rows)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        stop(proc, 'arduplane')
    with open(os.path.join(OUT, 'plane-guided-slew-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    print('[plane-guided-slew] %s' % (notes[-1] if notes else 'no notes'), flush=True)


def plane_guided_altitude_no_wp():
    """Isolates why GUIDED_CHANGE_ALTITUDE had no effect in plane_guided_slew(): there, GUIDED was reached via MAV_CMD_DO_REPOSITION, which also calls plane.set_guided_WP() (a position
    target with its own altitude). This reaches GUIDED by a plain mode switch instead (as plane_position() does, no DO_REPOSITION, no set_guided_WP call at all), then sends only
    GUIDED_CHANGE_ALTITUDE, to see whether the WP target set by DO_REPOSITION is what was overriding the altitude slew."""
    fresh()
    notes, proc = [], start_plane()
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        time.sleep(45)
        a, b = at(300, 0), at(300, 300)
        items = [mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, HOME[0], HOME[1], HOME[2]), mission.Item(1, 3, 22, 1, 1, 15.0, 0, 0, 0, 0.0, 0.0, 60.0),
                 mission.Item(2, 3, 16, 0, 1, 0, 0, 0, 0, a[0], a[1], 60.0), mission.Item(3, 3, 16, 0, 1, 0, 0, 0, 0, b[0], b[1], 60.0)]
        notes.append('upload ack %s' % mission.upload(conn, items))
        flight.set_mode(conn, 'MANUAL', table='plane')
        armed = flight.arm(conn, timeout=150.0)
        notes.append('arm: %s' % armed.detail)
        auto = flight.set_mode(conn, 'AUTO', table='plane')
        give_up = time.time() + 90.0
        while not auto.ok and time.time() < give_up:
            time.sleep(3)
            auto = flight.set_mode(conn, 'AUTO', table='plane')
        notes.append('AUTO: %s' % auto.detail)
        time.sleep(30)
        guided = flight.set_mode(conn, 'GUIDED', table='plane')          # plain mode switch, no DO_REPOSITION, no set_guided_WP call
        notes.append('GUIDED: %s' % guided.detail)
        t0, rows = time.time(), []

        def hold(seconds):
            end = time.time() + seconds
            while time.time() < end:
                r = track_row(conn, t0)
                if r:
                    rows.append(r)

        hold(5.0)
        conn.mav.command_int_send(conn.target_system, conn.target_component, mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT, 43001, 0, 0, 0, 0, 3.0, 0, 0, 0, 120.0)
        ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
        notes.append('t=%5.1f GUIDED_CHANGE_ALTITUDE to 120 m (no prior DO_REPOSITION): ack %s' % (time.time() - t0, None if ack is None else ack.result))
        hold(60.0)
        last = rows[-1] if rows else None
        if last:
            notes.append('final: alt %.1f m' % last[3])
        write_track('plane-guided-altitude-no-wp', rows)
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        stop(proc, 'arduplane')
    with open(os.path.join(OUT, 'plane-guided-altitude-no-wp-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    print('[plane-guided-altitude-no-wp] %s' % (notes[-1] if notes else 'no notes'), flush=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    if 'copter-position' in PARTS:
        copter_position()
    if 'copter-velocity' in PARTS:
        copter_velocity()
    if 'plane-position' in PARTS:
        plane_position()
    if 'plane-reposition' in PARTS:
        plane_reposition()
    if 'plane-guided-slew' in PARTS:
        plane_guided_slew()
    if 'plane-guided-altitude-no-wp' in PARTS:
        plane_guided_altitude_no_wp()
    return 0


if __name__ == '__main__':
    sys.exit(main())
