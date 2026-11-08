"""Append the sitl-copter-stick-modes results to the matching ap-mode:ArduCopter rows in coverage/claims.csv.

Reads sitl-evidence/copter-stick-modes/copter-stick-modes.csv and writes a short factual sentence per mode. Run once; it skips rows
that already mention the stick-modes evidence file.
"""
import csv
import io
import os
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, 'sitl-evidence', 'copter-stick-modes', 'copter-stick-modes.csv')
CLAIMS = os.path.join(ROOT, 'coverage', 'claims.csv')
EVID = 'sitl-evidence/copter-stick-modes/copter-stick-modes.csv;sitl-evidence/copter-stick-modes/copter-stick-modes.json;research-tools/sitl-copter-stick-modes.py;research-tools/run-copter-stick-modes.sh'

rows = list(csv.DictReader(open(RES, newline='')))


def sel(mode, pwm=None):
    return [r for r in rows if r['mode'] == mode and (pwm is None or str(r['stick_roll_pwm']) == str(pwm))]


def rng(vals):
    vals = [float(v) for v in vals]
    return '%.1f to %.1f' % (min(vals), max(vals)) if min(vals) != max(vals) else '%.1f' % vals[0]


def last04(mode, pwm):
    return rng([r['mean_roll_deg_last_0.4s'] for r in sel(mode, pwm)])


notes = {}
for m in ('STABILIZE', 'ALT_HOLD'):
    s = sel(m, 1700)
    notes['mode_' + m.lower().replace('_', '')] = (
        "Own stick test (disposable Copter SITL, 3 attempts): roll stick 1700 held 1 s gave a settled roll of %s degrees against my predicted %s "
        "(stick fraction after the RC1_DZ 20 deadzone times ATC_ANGLE_MAX 30)." % (last04(m, 1700), s[0]['predicted_angle_deg']))
notes['mode_sport'] = ("Own stick test (3 attempts each): roll stick 1600 gave peak roll rate %s dps and 1700 gave %s dps; roll angle after 1 s %s and %s degrees. "
                       "Observed response only, no formula checked." % (rng([r['peak_roll_rate_dps'] for r in sel('SPORT', 1600)]), rng([r['peak_roll_rate_dps'] for r in sel('SPORT', 1700)]),
                                                                       rng([r['peak_roll_deg'] for r in sel('SPORT', 1600)]), rng([r['peak_roll_deg'] for r in sel('SPORT', 1700)])))
notes['mode_acro'] = ("Own stick test (3 attempts each): roll stick 1600 gave peak roll rate %s dps and 1700 gave %s dps. With ACRO_RP_RATE 360 and ACRO_RP_EXPO 0.3 "
                      "the expo curve (1-e)x+e*x^3 on the deadzone-corrected stick gives about 42.5 and 100 dps (my formula, not read from source); observed values are within about 4%%."
                      % (rng([r['peak_roll_rate_dps'] for r in sel('ACRO', 1600)]), rng([r['peak_roll_rate_dps'] for r in sel('ACRO', 1700)])))
notes['mode_drift'] = ("Own stick test (3 attempts each): roll stick 1700 gave yaw rate %s dps and 1300 gave %s dps with roll under 0.2 degrees, i.e. the roll stick drives yaw as documented for Drift."
                       % (rng([r['peak_yaw_rate_dps'] for r in sel('DRIFT', 1700)]), rng([r['peak_yaw_rate_dps'] for r in sel('DRIFT', 1300)])))
g = sel('GUIDED_NOGPS')[0]
notes['mode_guided_nogps'] = ("Own test: SET_ATTITUDE_TARGET with a 10 degree roll at 0.5 thrust gave a settled roll of %s degrees (peak %s)." % (g['mean_roll_deg_last_0.4s'], g['peak_roll_deg']))
s = sel('SYSTEMID')[0]
notes['mode_systemid'] = ("Own test: with SID_AXIS=1 (roll angle, 5 degrees, 1 to 8 Hz) the mode started ('SystemID Starting: axis=1') only from STABILIZE, as mode_systemid.cpp:100-102 requires "
                          "(a manual-throttle mode); entry from LOITER was refused ('Axis requires manual throttle'). Roll standard deviation in SYSTEMID vs hover: %s. "
                          "After the sweep the vehicle lost height and hit the ground at 5.5 m/s because my fixed throttle was too low (test artefact). Logged SYSTEM_ID data not analysed."
                          % s['predicted_angle_deg'].replace('roll stdev loiter hover ', 'hover ').replace(' vs systemid ', ' vs '))

lines = open(CLAIMS, 'rb').read().decode('utf-8').split('\n')
out, changed = [], 0
for line in lines:
    key = line.split(',', 1)[0]
    if key.startswith('ap-mode:ArduCopter/'):
        mode = key.split('/', 1)[1]
        if mode in notes and 'copter-stick-modes' not in line:
            fields = next(csv.reader([line]))
            fields[6] = fields[6] + ';' + EVID
            fields[7] = fields[7].rstrip() + ' ' + notes[mode]
            buf = io.StringIO()
            csv.writer(buf, lineterminator='').writerow(fields)
            line = buf.getvalue()
            changed += 1
    out.append(line)
open(CLAIMS, 'wb').write('\n'.join(out).encode('utf-8'))
print('rows updated:', changed, sorted(notes))
