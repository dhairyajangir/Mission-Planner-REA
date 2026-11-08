"""AntennaTracker SITL test (WSL, pymavlink, disposable simulator): send a fake vehicle position stream, enter AUTO, and
compare the tracker's reported target bearing/pitch and servo outputs with independently computed geometry.

    python sitl-tracker-auto.py <antennatracker binary> <outdir>
"""
import csv
import json
import math
import os
import subprocess
import sys
import time

from pymavlink import mavutil

HOME = (-35.363261, 149.165230, 584.0)
R = 6371008.8


def offset(lat, lon, bearing, dist):
    p1, l1, b, d = math.radians(lat), math.radians(lon), math.radians(bearing), dist / R
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(b))
    l2 = l1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(p1), math.cos(d) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), math.degrees(l2)


def main():
    binary, outdir = sys.argv[1], sys.argv[2]
    # optional 3rd arg: ALT_SOURCE value to set (0 baro, 1 gps, 2 gps vehicle-only); optional 4th: "baro" also sends SCALED_PRESSURE
    alt_source = int(sys.argv[3]) if len(sys.argv) > 3 else None
    send_baro = len(sys.argv) > 4 and sys.argv[4] == 'baro'
    os.makedirs(outdir, exist_ok=True)
    log = open(os.path.join(outdir, 'sitl.log'), 'w')
    proc = subprocess.Popen([binary, '-w', '-M', 'tracker', '-I', '5', '-s', '1', '--home', '%f,%f,%f,0' % HOME], cwd=outdir, stdout=log, stderr=subprocess.STDOUT)
    rows, events = [], []
    try:
        m = None
        for _ in range(40):
            try:
                m = mavutil.mavlink_connection('tcp:127.0.0.1:5810', autoreconnect=False)
                break
            except Exception:
                time.sleep(0.5)
        m.wait_heartbeat(timeout=20)
        m.mav.request_data_stream_send(m.target_system, m.target_component, mavutil.mavlink.MAV_DATA_STREAM_ALL, 5, 1)
        # wait for the tracker's own position
        t0 = time.time()
        while time.time() - t0 < 90:
            msg = m.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=2)
            if msg is not None and msg.lat != 0:
                events.append(('tracker_position', msg.lat / 1e7, msg.lon / 1e7, msg.alt / 1000.0))
                break
        tracker_press = None
        if alt_source is not None:
            m.mav.param_set_send(m.target_system, m.target_component, b'ALT_SOURCE', float(alt_source), mavutil.mavlink.MAV_PARAM_TYPE_INT8)
            t0 = time.time()
            while time.time() - t0 < 10:
                msg = m.recv_match(type='PARAM_VALUE', blocking=True, timeout=1)
                if msg is not None and msg.param_id.rstrip('\x00') == 'ALT_SOURCE':
                    events.append(('alt_source_readback', msg.param_value))
                    break
        if send_baro:
            msg = m.recv_match(type='SCALED_PRESSURE', blocking=True, timeout=5)
            tracker_press = msg.press_abs if msg is not None else None
            events.append(('tracker_press_hpa', tracker_press))
        cases = [(90, 500, 100), (0, 500, 100), (180, 800, 50), (270, 300, 150), (45, 1000, 0)]
        for brg, dist, up in cases:
            vlat, vlon = offset(HOME[0], HOME[1], brg, dist)
            m.set_mode(m.mode_mapping()['AUTO'])
            end = time.time() + 14
            seen = {'nav_bearing': None, 'target_bearing': None, 'pitch': None, 'servo1': None, 'servo2': None}
            while time.time() < end:
                # fake vehicle (system 2) position report, 5 Hz
                m.mav.srcSystem = 2
                m.mav.global_position_int_send(int(time.time() * 1000) & 0xFFFFFFFF, int(vlat * 1e7), int(vlon * 1e7), int((HOME[2] + up) * 1000), int(up * 1000), 0, 0, 0, 0)
                if send_baro and tracker_press:
                    # isothermal approximation of pressure at 'up' metres above the tracker
                    vp = tracker_press * math.exp(-up / 8434.5)
                    m.mav.scaled_pressure_send(int(time.time() * 1000) & 0xFFFFFFFF, vp, 0.0, 1500)
                m.mav.srcSystem = 255
                t1 = time.time() + 0.2
                while time.time() < t1:
                    msg = m.recv_match(blocking=True, timeout=0.2)
                    if msg is None:
                        continue
                    t = msg.get_type()
                    if t == 'NAV_CONTROLLER_OUTPUT':
                        seen['nav_bearing'], seen['target_bearing'] = msg.nav_bearing, msg.target_bearing
                        seen['pitch'] = msg.nav_pitch
                    elif t == 'SERVO_OUTPUT_RAW':
                        seen['servo1'], seen['servo2'] = msg.servo1_raw, msg.servo2_raw
            exp_el = math.degrees(math.atan2(up, dist))
            rows.append({'bearing_deg': brg, 'distance_m': dist, 'height_m': up, 'expected_elevation_deg': round(exp_el, 2), **seen})
            print(rows[-1], flush=True)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        log.close()
    with open(os.path.join(outdir, 'tracker-auto.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, list(rows[0].keys()) if rows else ['bearing_deg'], lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    json.dump({'events': events, 'rows': rows}, open(os.path.join(outdir, 'tracker-auto.json'), 'w'), indent=1, default=str)


if __name__ == '__main__':
    main()
