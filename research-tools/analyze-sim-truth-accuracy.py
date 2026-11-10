"""How close are the vehicle's own estimates to the simulator's ground truth? DataFlash logs of the simulated flights carry a `SIM` message (the simulator's true attitude, latitude, longitude and
altitude) next to the estimates the firmware wrote: `ATT` (the AHRS attitude), `XKF1` (EKF3 core 0 attitude), `AHR2`, `POS` (AHRS position), `BARO` (barometer altitude) and `GPS`.
Simulator only: the "truth" is the simulator's model, and the sensors are its models of sensors, so this checks the firmware's estimation against the simulation, not against an aircraft.

    python3 analyze-sim-truth-accuracy.py <dir with *.BIN.gz> <out csv> [log name ...]

For every pair (estimate, truth) the nearest earlier `SIM` sample in time is used. Statistics are given over the whole log and over the part where the simulated altitude is more than 1 m
above the first sample ("airborne"). Angles are compared modulo 360 degrees; positions as horizontal distance in metres and altitude difference in metres.
"""
import bisect
import csv
import gzip
import math
import os
import shutil
import sys
import tempfile

from pymavlink import DFReader

SRC, OUT = sys.argv[1], sys.argv[2]
NAMES = sys.argv[3:] or ['copter-logged-flight-00000001.BIN.gz', 'plane-logged-flight-00000001.BIN.gz', 'custom-mode-00000001.BIN.gz', 'heli-acro-00000001.BIN.gz']
M_LAT = 111320.0
TYPES = ['SIM', 'ATT', 'XKF1', 'AHR2', 'POS', 'BARO', 'GPS']


def angle_diff(a, b):
    return (a - b + 180.0) % 360.0 - 180.0


def stats(values):
    if not values:
        return None
    values = sorted(abs(v) for v in values)
    n = len(values)
    return {'n': n, 'mean_abs': sum(values) / n, 'rms': math.sqrt(sum(v * v for v in values) / n), 'p95': values[min(n - 1, int(0.95 * n))], 'max': values[-1]}


def load(path):
    tmp = os.path.join(tempfile.gettempdir(), os.path.basename(path)[:-3])
    with gzip.open(path, 'rb') as s, open(tmp, 'wb') as o:
        shutil.copyfileobj(s, o)
    log = DFReader.DFReader_binary(tmp)
    data = {t: [] for t in TYPES}
    while True:
        m = log.recv_match(type=TYPES)
        if m is None:
            break
        data[m.get_type()].append(m.to_dict())
    os.remove(tmp)
    return data


def analyse(name, data):
    sim = data['SIM']
    if not sim:
        return []
    times = [r['TimeUS'] for r in sim]
    alt0 = sim[0]['Alt']

    def truth(t):
        i = bisect.bisect_right(times, t) - 1
        return sim[i] if i >= 0 else None

    cases = [  # label, message, extractor of (kind, estimate values), compared to truth
        ('AHRS roll (ATT)', 'ATT', 'angle', lambda r, s: angle_diff(r['Roll'], s['Roll'])),
        ('AHRS pitch (ATT)', 'ATT', 'angle', lambda r, s: angle_diff(r['Pitch'], s['Pitch'])),
        ('AHRS yaw (ATT)', 'ATT', 'angle', lambda r, s: angle_diff(r['Yaw'], s['Yaw'])),
        ('EKF3 core 0 roll (XKF1)', 'XKF1', 'angle', lambda r, s: angle_diff(r['Roll'], s['Roll'])),
        ('EKF3 core 0 pitch (XKF1)', 'XKF1', 'angle', lambda r, s: angle_diff(r['Pitch'], s['Pitch'])),
        ('EKF3 core 0 yaw (XKF1)', 'XKF1', 'angle', lambda r, s: angle_diff(r['Yaw'], s['Yaw'])),
        ('AHRS position horizontal (POS)', 'POS', 'metres', lambda r, s: math.hypot((r['Lat'] - s['Lat']) * M_LAT, (r['Lng'] - s['Lng']) * M_LAT * math.cos(math.radians(s['Lat'])))),
        ('AHRS altitude (POS)', 'POS', 'metres', lambda r, s: r['Alt'] - s['Alt']),
        ('barometer altitude (BARO AltAMSL)', 'BARO', 'metres', lambda r, s: r['AltAMSL'] - s['Alt']),
        ('GPS position horizontal (GPS)', 'GPS', 'metres', lambda r, s: math.hypot((r['Lat'] - s['Lat']) * M_LAT, (r['Lng'] - s['Lng']) * M_LAT * math.cos(math.radians(s['Lat'])))),
        ('GPS altitude (GPS)', 'GPS', 'metres', lambda r, s: r['Alt'] - s['Alt']),
    ]
    rows = []
    for label, msg, unit, fn in cases:
        both, air = [], []
        for r in data[msg]:
            if msg == 'XKF1' and r.get('C', 0) != 0:
                continue
            if msg == 'BARO' and r.get('I', 0) != 0:
                continue
            if msg == 'GPS' and r.get('I', 0) != 0:
                continue
            s = truth(r['TimeUS'])
            if s is None:
                continue
            v = fn(r, s)
            both.append(v)
            if s['Alt'] - alt0 > 1.0:
                air.append(v)
        for part, vals in (('whole log', both), ('airborne', air)):
            st = stats(vals)
            if st:
                rows.append([name, label, part, unit, st['n'], round(st['mean_abs'], 4), round(st['rms'], 4), round(st['p95'], 4), round(st['max'], 4)])
    return rows


def main():
    rows = []
    for name in NAMES:
        path = os.path.join(SRC, name)
        if not os.path.exists(path):
            print('missing', path)
            continue
        rows += analyse(name.replace('-00000001.BIN.gz', ''), load(path))
    with open(OUT, 'w', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['log', 'estimate', 'part', 'unit', 'n', 'mean_abs', 'rms', 'p95', 'max'])
        w.writerows(rows)
    for r in rows:
        if r[2] == 'airborne':
            print(r)


if __name__ == '__main__':
    main()
