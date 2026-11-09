"""List, from the gzipped Copter autotest log, which simulator frames the Copter suite's FlyEachFrame test flew and which it skipped, with the reason it printed.

    python build-fly-each-frame-table.py <Copter.log.gz> <out csv>
"""
import csv
import gzip
import re
import sys

log, out = sys.argv[1:3]
text = gzip.open(log, 'rt', errors='replace').read()
end = text.index('PASSED: "FlyEachFrame')
head = text.rfind('FlyEachFrame', 0, end)
# the first "Testing frame" header after the test started
start = text.index('Testing frame (', head)
start = text.rfind('-', 0, start) if text.rfind('-', 0, start) > start - 20 else start
segment = text[start:end]
parts = re.split(r'-+ Testing frame \(([^)]+)\)\s+-+', segment)
rows = []
# parts[0] is text before the first header (empty if the first header was cut); headers and bodies alternate after it
names = parts[1::2]
bodies = parts[2::2]
first = re.search(r'Testing frame \(([^)]+)\)', text[head:end])
if first and first.group(1) not in names:
    names.insert(0, first.group(1))
    bodies.insert(0, parts[0])
for name, body in zip(names, bodies):
    m = re.search(r"Actually, no I'm not - ([^\n]+)", body)
    rows.append([name, 'skipped' if m else 'flown (take off to 10 m, hover, ALT_HOLD with yaw pulses, RTL)', m.group(1) if m else ''])
with open(out, 'w', newline='') as f:
    w = csv.writer(f, lineterminator='\n')
    w.writerow(['frame', 'outcome', 'reason_printed_when_skipped'])
    w.writerows(rows)
print(len(rows), 'frames;', sum(r[1] == 'skipped' for r in rows), 'skipped')
