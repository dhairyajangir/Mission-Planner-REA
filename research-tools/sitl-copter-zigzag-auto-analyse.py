"""Per-leg table for sitl-copter-zigzag-auto.py output: for each 'ZigZag: moving to ...' / 'manual control' text, the position (NED north/east, from LOCAL_POSITION_NED)
at the text and at the next text, so each auto leg's displacement is measured, not assumed.  Usage: python sitl-copter-zigzag-auto-analyse.py <evidence dir>"""
import csv
import json
import math
import os
import re
import sys

d = sys.argv[1]
rows = {}
with open(os.path.join(d, 'zigzag-track.csv')) as f:
    for r in csv.DictReader(f):
        rows.setdefault(r['case'], []).append((float(r['seconds']), float(r['north_m']), float(r['east_m']), r['mode']))
texts = []
for line in open(os.path.join(d, 'zigzag-notes.txt')):
    m = re.match(r't=\s*([\d.]+) vehicle: (ZigZag: .*)', line)
    if m:
        texts.append((float(m.group(1)), m.group(2)))
summ = json.load(open(os.path.join(d, 'zigzag-summary.json')))


def pos_at(case, t):
    return min(rows[case], key=lambda x: abs(x[0] - t))


out = []
for s in summ:
    c = s['case']
    t0 = s['pos_at_auto']
    ev = [(t, x) for t, x in texts if rows[c][0][0] <= t <= rows[c][-1][0] and ('moving to' in x or 'manual control' in x)]
    ev = [(t, x) for t, x in ev if t >= pos_at(c, 0)[0]]
    legs = []
    for i, (t, x) in enumerate(ev[:-1]):
        a, b = pos_at(c, t), pos_at(c, ev[i + 1][0])
        legs.append({'text': x, 't_start': t, 't_end': ev[i + 1][0], 'dN': round(b[1] - a[1], 1), 'dE': round(b[2] - a[2], 1), 'len': round(math.hypot(b[1] - a[1], b[2] - a[2]), 1),
                     'start_NE': (round(a[1], 1), round(a[2], 1)), 'end_NE': (round(b[1], 1), round(b[2], 1)), 'end_text': ev[i + 1][1]})
    out.append({'case': c, 'A_NE': (round(s['pos_a'][0], 1), round(s['pos_a'][1], 1)), 'B_NE': (round(s['pos_b'][0], 1), round(s['pos_b'][1], 1)), 'legs': legs})
json.dump(out, open(os.path.join(d, 'zigzag-legs.json'), 'w'), indent=1)
with open(os.path.join(d, 'zigzag-legs.txt'), 'w') as f:
    for o in out:
        f.write('%s  A=%s B=%s\n' % (o['case'], o['A_NE'], o['B_NE']))
        for l in o['legs']:
            f.write('   %6.1f-%6.1f s  %-34s dN=%6.1f dE=%6.1f len=%5.1f  ends with: %s\n' % (l['t_start'], l['t_end'], l['text'], l['dN'], l['dE'], l['len'], l['end_text']))
print(open(os.path.join(d, 'zigzag-legs.txt')).read())
