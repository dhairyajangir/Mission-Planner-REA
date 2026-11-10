"""How well does the firmware's controller follow its own targets in the simulated flights? From the saved DataFlash logs: desired against actual values the firmware logs itself. Simulator only.

    python3 analyze-control-tracking.py <dir with *.BIN.gz> <out csv> [log name ...]

Copter logs: `ANG` (desired and actual roll, pitch, yaw), `RATE` (desired and actual body rates), `CTUN` (desired and actual altitude), `PSCN`/`PSCE` (position and velocity target against
actual, north and east). Plane logs: `CTUN` (navigation roll and pitch against actual), `TECS` (height and speed demand against actual), `NTUN` (altitude error, cross-track error, airspeed
error). Battery: `BAT` voltage, current and remaining percentage. Only airborne samples are used (Copter `CTUN.Alt` above 1 m, Plane `TECS.h` above 5 m). The targets are the firmware's own, so this
shows how closely it tracks what it decided, not whether the targets were right.
"""
import csv
import gzip
import math
import os
import shutil
import sys
import tempfile

from pymavlink import DFReader

SRC, OUT = sys.argv[1], sys.argv[2]
NAMES = sys.argv[3:] or ['copter-logged-flight-00000001.BIN.gz', 'plane-logged-flight-00000001.BIN.gz', 'custom-mode-00000001.BIN.gz']
TYPES = ['ANG', 'RATE', 'CTUN', 'PSCN', 'PSCE', 'TECS', 'NTUN', 'BAT']


def wrap(a):
    return (a + 180.0) % 360.0 - 180.0


def stats(values):
    if not values:
        return None
    v = sorted(abs(x) for x in values)
    n = len(v)
    return n, sum(v) / n, math.sqrt(sum(x * x for x in v) / n), v[min(n - 1, int(0.95 * n))], v[-1]


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


def windows(rows, flying):
    """[(start, end)] time ranges (TimeUS) where flying(row) holds."""
    out, start, last = [], None, None
    for r in rows:
        if flying(r):
            start = r['TimeUS'] if start is None else start
            last = r['TimeUS']
        elif start is not None:
            out.append((start, last))
            start = None
    if start is not None:
        out.append((start, last))
    return out


def inside(t, wins):
    return any(a <= t <= b for a, b in wins)


def analyse(name, d):
    rows = []

    def add(label, unit, values):
        s = stats(values)
        if s:
            rows.append([name, label, unit, s[0], round(s[1], 4), round(s[2], 4), round(s[3], 4), round(s[4], 4)])

    copter = bool(d['PSCN']) or bool(d['ANG'])
    if copter:
        wins = windows(d['CTUN'], lambda r: r['Alt'] > 1.0)
        add('roll: desired - actual (ANG)', 'deg', [wrap(r['DesRoll'] - r['Roll']) for r in d['ANG'] if inside(r['TimeUS'], wins)])
        add('pitch: desired - actual (ANG)', 'deg', [wrap(r['DesPitch'] - r['Pitch']) for r in d['ANG'] if inside(r['TimeUS'], wins)])
        add('yaw: desired - actual (ANG)', 'deg', [wrap(r['DesYaw'] - r['Yaw']) for r in d['ANG'] if inside(r['TimeUS'], wins)])
        add('roll rate: desired - actual (RATE)', 'deg/s', [r['RDes'] - r['R'] for r in d['RATE'] if inside(r['TimeUS'], wins)])
        add('pitch rate: desired - actual (RATE)', 'deg/s', [r['PDes'] - r['P'] for r in d['RATE'] if inside(r['TimeUS'], wins)])
        add('yaw rate: desired - actual (RATE)', 'deg/s', [r['YDes'] - r['Y'] for r in d['RATE'] if inside(r['TimeUS'], wins)])
        add('altitude: desired - actual (CTUN DAlt - Alt)', 'm', [r['DAlt'] - r['Alt'] for r in d['CTUN'] if r['Alt'] > 1.0])
        add('position north: target - actual (PSCN)', 'm', [r['TPN'] - r['PN'] for r in d['PSCN'] if inside(r['TimeUS'], wins)])
        add('position east: target - actual (PSCE)', 'm', [r['TPE'] - r['PE'] for r in d['PSCE'] if inside(r['TimeUS'], wins)])
        add('velocity north: target - actual (PSCN)', 'm/s', [r['TVN'] - r['VN'] for r in d['PSCN'] if inside(r['TimeUS'], wins)])
        add('velocity east: target - actual (PSCE)', 'm/s', [r['TVE'] - r['VE'] for r in d['PSCE'] if inside(r['TimeUS'], wins)])
    else:
        wins = windows(d['TECS'], lambda r: r['h'] > 5.0)
        add('roll: navigation demand - actual (CTUN)', 'deg', [r['NavRoll'] - r['Roll'] for r in d['CTUN'] if 'NavRoll' in r and inside(r['TimeUS'], wins)])
        add('pitch: navigation demand - actual (CTUN)', 'deg', [r['NavPitch'] - r['Pitch'] for r in d['CTUN'] if 'NavPitch' in r and inside(r['TimeUS'], wins)])
        add('height: demand - actual (TECS hdem - h)', 'm', [r['hdem'] - r['h'] for r in d['TECS'] if r['h'] > 5.0])
        add('speed: demand - actual (TECS spdem - sp)', 'm/s', [r['spdem'] - r['sp'] for r in d['TECS'] if r['h'] > 5.0])
        add('altitude error (NTUN AltE)', 'm', [r['AltE'] for r in d['NTUN'] if inside(r['TimeUS'], wins)])
        add('cross-track error (NTUN XT)', 'm', [r['XT'] for r in d['NTUN'] if inside(r['TimeUS'], wins)])
        add('airspeed error (NTUN AsE)', 'm/s', [r['AsE'] for r in d['NTUN'] if inside(r['TimeUS'], wins)])
    bat = d['BAT']
    if bat:
        volts = [r['Volt'] for r in bat]
        curr = [r['Curr'] for r in bat]
        rows.append([name, 'battery (BAT): voltage min / max, current mean / max, remaining first -> last', 'V, A, %', len(bat), round(min(volts), 3), round(max(volts), 3),
                     '%.2f / %.2f' % (sum(curr) / len(curr), max(curr)), '%s -> %s' % (bat[0]['RemPct'], bat[-1]['RemPct'])])
    return rows


def main():
    rows = []
    for name in NAMES:
        path = os.path.join(SRC, name)
        if os.path.exists(path):
            rows += analyse(name.replace('-00000001.BIN.gz', ''), load(path))
    with open(OUT, 'w', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['log', 'metric', 'unit', 'n', 'mean_abs', 'rms', 'p95', 'max'])
        w.writerows(rows)
    for r in rows:
        print(r)


if __name__ == '__main__':
    main()
