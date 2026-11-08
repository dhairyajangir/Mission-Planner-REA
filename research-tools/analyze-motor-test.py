"""Line up the PageMotorTestProbe action log (UTC wall-clock times) with the independent SERVO_OUTPUT_RAW observer and summarise, per page action,
the idle and the in-window servo outputs for servo1..servo4. Also lists the vehicle's own motor-test STATUSTEXT lines.

    python analyze-motor-test.py <motor-test-page evidence folder>
"""
import csv
import datetime
import os
import re
import sys

d = sys.argv[1]
actions = {}
for line in open(os.path.join(d, 'motor-test-page-log.txt')):
    m = re.match(r'(\S+) ACTION-(START|RETURNED|END) (\S+)', line)
    if m:
        t = datetime.datetime.strptime(m.group(1)[:26] + 'Z', '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=datetime.timezone.utc).timestamp()
        actions.setdefault(m.group(3), {})[m.group(2)] = t
rows = [[float(r[0])] + [int(x) for x in r[1:5]] for r in list(csv.reader(open(os.path.join(d, 'servo-observer.csv'))))[1:]]
print('observer samples:', len(rows), 'from', rows[0][0], 'to', rows[-1][0])
first_action = min(a['START'] for a in actions.values())
idle = [r for r in rows if r[0] < first_action - 0.5]
base = [sorted(r[i] for r in idle)[len(idle) // 2] for i in range(1, 5)]
print('idle median PWM before the first action (servo1..4):', base, 'from', len(idle), 'samples')
out = [['action', 'window_s', 'servo1_min', 'servo1_max', 'servo2_min', 'servo2_max', 'servo3_min', 'servo3_max', 'servo4_min', 'servo4_max', 'servos_above_idle_by_20us_or_more']]
for name in ('but_TestAll', 'but_TestAllSeq', 'but_StopAll'):
    a = actions[name]
    w = [r for r in rows if a['START'] <= r[0] <= a['END']]
    cells = []
    moved = []
    for i in range(1, 5):
        vals = [r[i] for r in w]
        cells += [min(vals), max(vals)]
        if max(vals) >= base[i - 1] + 20:
            moved.append('servo%d' % i)
    out.append([name, '%.1f' % (a['END'] - a['START'])] + cells + [' '.join(moved) or 'none'])
    print(name, 'window %.1f s:' % (a['END'] - a['START']), dict(zip(['s1min', 's1max', 's2min', 's2max', 's3min', 's3max', 's4min', 's4max'], cells)), 'moved:', moved or 'none')
# sequence order: first time each servo exceeds idle+20 within the sequence window
a = actions['but_TestAllSeq']
order = []
for i in range(1, 5):
    t = next((r[0] for r in rows if a['START'] <= r[0] <= a['END'] and r[i] >= base[i - 1] + 20), None)
    order.append((t - a['START']) if t else None)
print('seconds after but_TestAllSeq until each servo first rises:', [None if x is None else round(x, 1) for x in order])
with open(os.path.join(d, 'motor-test-summary.csv'), 'w', newline='') as f:
    csv.writer(f, lineterminator='\n').writerows(out)
st = [l.strip() for l in open(os.path.join(d, 'servo-observer.statustext.txt')) if 'motor' in l.lower()]
print('vehicle motor-test messages:', st)
