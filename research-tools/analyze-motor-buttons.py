"""Line up the PageMotorButtonsProbe action log (UTC wall-clock times) with the independent SERVO_OUTPUT_RAW observer: for each action, which servo outputs left their idle
value by 20 microseconds or more (either direction) during the action's window, and by how much at most.

    python analyze-motor-buttons.py <folder with <label>-log.txt and <label>-servo-observer.csv> <label> <out csv>
"""
import csv
import datetime
import os
import re
import sys

d, label, out = sys.argv[1:4]
actions = []        # (name, start, end)
cur = {}
for line in open(os.path.join(d, label + '-log.txt'), encoding='utf-8-sig'):
    m = re.match(r'(\S+) ACTION-(START|END) (\S+)', line)
    if m:
        t = datetime.datetime.strptime(m.group(1)[:26] + 'Z', '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=datetime.timezone.utc).timestamp()
        if m.group(2) == 'START':
            cur[m.group(3)] = t
        else:
            actions.append((m.group(3), cur[m.group(3)], t))
    elif 'NO-BUTTON' in line or 'ACTION-EXCEPTION' in line or 'MESSAGEBOX' in line or 'BUTTON text=' in line:
        print(line.strip()[:200])
rows = [[float(r[0])] + [int(x) for x in r[1:9]] for r in list(csv.reader(open(os.path.join(d, label + '-servo-observer.csv'))))[1:]]
first = min(a[1] for a in actions)
idle_rows = [r for r in rows if r[0] < first - 0.5]
idle = [sorted(r[i] for r in idle_rows)[len(idle_rows) // 2] for i in range(1, 9)]
print('idle median servo1..8:', idle, 'from', len(idle_rows), 'samples')
res = [['action', 'servos_moved_20us_or_more', 'max_deviation_us_per_servo1_to_8']]
for name, a, b in actions:
    w = [r for r in rows if a <= r[0] <= b]
    dev = [max((abs(r[i + 1] - idle[i]) for r in w), default=0) for i in range(8)]
    moved = ['servo%d' % (i + 1) for i in range(8) if dev[i] >= 20]
    res.append([name, ' '.join(moved) or 'none', ' '.join(map(str, dev))])
    print(name, '->', ' '.join(moved) or 'none', dev)
with open(out, 'w', newline='') as f:
    csv.writer(f, lineterminator='\n').writerows(res)
