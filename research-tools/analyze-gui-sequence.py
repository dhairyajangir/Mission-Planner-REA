"""Order in which servo outputs 1..4 first rose above idle during the "Test all in Sequence" press recorded by run-live-gui-motor-test.ps1.

    python analyze-gui-sequence.py <live-gui-driven folder>
"""
import csv
import datetime
import os
import re
import sys

d = sys.argv[1]
t = {}
for line in open(os.path.join(d, 'gui-motor-test-log.txt'), encoding='utf-8-sig'):
    m = re.match(r'(\S+) ACTION-(START|END) (\S+)', line)
    if m:
        t[(m.group(3), m.group(2))] = datetime.datetime.strptime(m.group(1)[:26] + 'Z', '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=datetime.timezone.utc).timestamp()
a, b = t[('gui-test-all-in-sequence', 'START')], t[('gui-test-all-in-sequence', 'END')]
rows = [[float(r[0])] + [int(x) for x in r[1:5]] for r in list(csv.reader(open(os.path.join(d, 'gui-motor-test-servo-observer.csv'))))[1:]]
idle = [1000] * 4
first = {}
for r in rows:
    if a <= r[0] <= b:
        for i in range(4):
            if r[i + 1] >= idle[i] + 20 and i not in first:
                first[i] = r[0] - a
order = sorted(first, key=first.get)
print('servo outputs in order of first rise after the press (seconds after the press):', [(i + 1, round(first[i], 1)) for i in order])
