"""For one "Test all in Sequence" press recorded by run-live-gui-vehicles.ps1: the order in which servo outputs 1..8 first left their idle value (median before the press)
by 20 us or more, in either direction, during the press window; compared with the order the sweep (sitl-evidence/frame-motor-sweep/frame-sweep-sequences.csv) saw for the same frame.

    python analyze-gui-sequence-generic.py <folder> <label> <sweep frame name or ''>
"""
import csv
import datetime
import os
import re
import sys

d, label, sweep_frame = sys.argv[1:4]
t = {}
for line in open(os.path.join(d, label + '-log.txt'), encoding='utf-8-sig'):
    m = re.match(r'(\S+) ACTION-(START|END) (\S+)', line)
    if m:
        t[m.group(2)] = datetime.datetime.strptime(m.group(1)[:26] + 'Z', '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=datetime.timezone.utc).timestamp()
a, b = t['START'], t['END']
rows = [[float(r[0])] + [int(x) for x in r[1:9]] for r in list(csv.reader(open(os.path.join(d, label + '-servo-observer.csv'))))[1:]]
pre = [r for r in rows if r[0] < a - 0.3]
idle = [sorted(r[i] for r in pre)[len(pre) // 2] for i in range(1, 9)] if pre else [0] * 8
first = {}
for r in rows:
    if a <= r[0] <= b:
        for i in range(8):
            if abs(r[i + 1] - idle[i]) >= 20 and i not in first:
                first[i] = r[0] - a
order = [i + 1 for i in sorted(first, key=first.get)]
result = ['gui_order=' + ' '.join(map(str, order)), 'idle=' + ' '.join(map(str, idle))]
if sweep_frame:
    seq = {}
    for r in csv.DictReader(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(d))), 'sitl-evidence', 'frame-motor-sweep', 'frame-sweep-sequences.csv'))):
        seq.setdefault(r['frame'], []).append((int(r['sequence']), r['observed_servos_moved_20us_or_more']))
    swept = [x for _, x in sorted(seq.get(sweep_frame, []))]
    result.append('sweep_order=' + ' '.join(swept))
    result.append('same=' + str(' '.join(map(str, order)) == ' '.join(swept)))
print(' | '.join(result))
