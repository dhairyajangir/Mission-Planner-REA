"""First direct test of AP_Avoidance (ADSB-based collision avoidance, previously only autotest-name-matched) and AP_ADSB (previously gtest-level only - no
flight, no integration).

Two self-corrections on the way to this version, both worth keeping: (1) SIM_ADSB_RADIUS/SIM_ADSB_ALT only matter for SITL's own randomly-spawned intruder,
which is delivered through a simulated serial device (SIM_ADSB.cpp, a SerialDevice), not automatically wired up by ADSB_TYPE alone - confirmed by reading
AP_HAL_SITL/SITL_State_common.cpp's `streq(name, "adsb")` dispatch, which only fires for a `--serial5 sim:adsb`-style command-line device spec, not a param.
(2) Even after wiring that device up correctly (confirmed via the SITL log's "SIM connection adsb:(null) on SERIAL5" line), still nothing arrived: re-reading
AP_ADSB.cpp's own parameter doc clarified that ADSB_TYPE=1 ("MAVLink") does not decode a serial byte-level protocol at all - it processes incoming MAVLink
ADSB_VEHICLE messages arriving on any MAVLink channel, exactly as a companion computer with no ADS-B hardware would send them (GCS_Common.cpp's own
MAVLINK_MSG_ID_ADSB_VEHICLE handler confirms this). SIM_ADSB's serial device is for the other, hardware-protocol ADSB_TYPE values, not this one.

So this version drops the serial-device detour entirely and synthesizes the intruder directly over the same MAVLink link already used for everything else in
this project (the same technique already used for AP_Follow's synthetic target) - sending `ADSB_VEHICLE` MAVLink messages for a fabricated nearby aircraft,
closing in from 150m east at 15 m/s, same altitude. AVD_ENABLE=1 and AVD_F_ACTION=5 (RTL) make Copter::AP_Avoidance_Copter react to it. Simulator only.

    python3 sitl-copter-adsb-avoidance.py <ardupilot tree> <out dir> <custom-gcs dir>
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

HOME = (-35.363261, 149.165230, 584.0)
M_LAT = 111320.0
M_LON = M_LAT * math.cos(math.radians(HOME[0]))
WORK = os.path.expanduser('~/cg-copter-adsb-avoidance')
BIN = os.path.join(TREE, 'build/sitl/bin/arducopter')
TABLE = 'copter'
TAKEOFF_ALT_M = 20.0
INTRUDER_START_EAST_M = 150.0
INTRUDER_SPEED_MS = 15.0


def send_intruder(conn, east_offset_m, alt_amsl_mm):
    lat = int(HOME[0] * 1e7)
    lon = int((HOME[1] + east_offset_m / M_LON) * 1e7)
    conn.mav.adsb_vehicle_send(
        4242, lat, lon, 0, int(alt_amsl_mm), 27000, int(INTRUDER_SPEED_MS * 100), 0,
        b'SIM4242', 1, 0, 1 | 2 | 4 | 8 | 16, 1200)  # heading 270.00 deg (west, closing on home), flags: coords+alt+heading+velocity+callsign valid


def main():
    os.makedirs(OUT, exist_ok=True)
    subprocess.call(['pkill', '-x', 'arducopter'])
    time.sleep(1)
    subprocess.call(['rm', '-rf', WORK])
    os.makedirs(WORK)
    notes, track = [], []
    proc = subprocess.Popen([BIN, '-w', '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME],
                            cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'w'), stderr=subprocess.STDOUT)
    try:
        conn, _ = link.connect(5760, timeout=120.0)
        time.sleep(30)
        base = link.read_params(conn)
        want = {'ADSB_TYPE': 1.0, 'AVD_ENABLE': 1.0, 'AVD_F_ACTION': 5.0, 'AVD_F_DIST_XY': 1000.0, 'AVD_F_DIST_Z': 1000.0}
        bad = [r.name for r in params.write(conn, [params.Change(n, base.get(n), v) for n, v in want.items()]) if not r.ok]
        notes.append('set %s; rejected %s; restarting under the new setting' % (want, bad))
        time.sleep(2)
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
        proc = subprocess.Popen([BIN, '--model', '+', '-I', '0', '-s', '1', '--home', '%s,%s,%s,0' % HOME],
                                cwd=WORK, stdout=open(os.path.join(WORK, 'sitl.log'), 'a'), stderr=subprocess.STDOUT)
        conn, _ = link.connect(5760, timeout=180.0)
        time.sleep(30)
        after = link.read_params(conn)
        notes.append('after restart: ADSB_TYPE=%s AVD_ENABLE=%s AVD_F_ACTION=%s' % (after.get('ADSB_TYPE'), after.get('AVD_ENABLE'), after.get('AVD_F_ACTION')))
        conn.mav.command_long_send(conn.target_system, conn.target_component, 511, 0, 33, 100000, 0, 0, 0, 0, 0)  # GLOBAL_POSITION_INT 10Hz

        flight.set_mode(conn, 'GUIDED', table=TABLE)
        armed = flight.arm(conn, timeout=120.0)
        notes.append('arm: %s' % armed.detail)
        if armed.ok:
            conn.mav.command_long_send(conn.target_system, conn.target_component, 22, 0, 0, 0, 0, 0, 0, 0, TAKEOFF_ALT_M)
            conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
            time.sleep(25.0)

            alt_amsl_mm = int((HOME[2] + TAKEOFF_ALT_M) * 1000)
            t0 = time.time()
            last_send = 0.0
            while time.time() - t0 < 60.0:
                t = time.time() - t0
                if t - last_send >= 0.5:
                    east_m = max(0.0, INTRUDER_START_EAST_M - INTRUDER_SPEED_MS * t)
                    send_intruder(conn, east_m, alt_amsl_mm)
                    last_send = t
                msg = conn.recv_match(type=['GLOBAL_POSITION_INT', 'STATUSTEXT', 'HEARTBEAT'], blocking=True, timeout=0.3)
                if msg is None:
                    continue
                kind = msg.get_type()
                if kind == 'STATUSTEXT':
                    notes.append('t=%5.1f vehicle: %s' % (t, msg.text))
                elif kind == 'GLOBAL_POSITION_INT':
                    track.append([round(t, 1), msg.relative_alt / 1000.0])
                elif kind == 'HEARTBEAT' and msg.get_srcComponent() == 1 and msg.type not in (6, 27):
                    notes.append('t=%5.1f armed=%s custom_mode=%s intruder_east_m=%.0f' %
                                 (t, flight.is_armed(msg), msg.custom_mode, max(0.0, INTRUDER_START_EAST_M - INTRUDER_SPEED_MS * t)))
    except Exception as e:
        notes.append('EXCEPTION %r' % (e,))
    finally:
        subprocess.call(['pkill', '-TERM', '-x', 'arducopter'])
        try:
            proc.wait(120)
        except Exception:
            proc.kill()
    with open(os.path.join(OUT, 'adsb-avoidance-notes.txt'), 'w') as f:
        f.write('\n'.join(notes) + '\n')
    with open(os.path.join(OUT, 'adsb-avoidance-track.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['seconds', 'relative_alt_m'])
        w.writerows(track)
    print('[adsb-avoidance] %d track rows; last 5: %s' % (len(track), track[-5:]), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
