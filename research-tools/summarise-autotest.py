"""Compute the final status of each autotest per vehicle from sitl-evidence/autotest/autotest-results.csv.

Rows are in run order (collect-autotest.sh appends logs in the order given), so a later row for the same test overrides
an earlier one. Writes autotest-final.csv (vehicle,test,final_result,runs) next to the input and prints a summary.

    python summarise-autotest.py <path to autotest-results.csv>
"""
import csv
import os
import sys
from collections import OrderedDict

src = sys.argv[1]
final = OrderedDict()
with open(src, newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        vehicle = row['label'].split('-')[0]
        key = (vehicle, row['test'])
        entry = final.setdefault(key, {'result': None, 'runs': []})
        entry['result'] = row['result']
        entry['runs'].append(row['label'] + ':' + row['result'])

out = os.path.join(os.path.dirname(src), 'autotest-final.csv')
with open(out, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f, lineterminator='\n')
    w.writerow(['vehicle', 'test', 'final_result', 'runs'])
    for (vehicle, test), e in final.items():
        w.writerow([vehicle, test, e['result'], ' | '.join(e['runs'])])

per = OrderedDict()
for (vehicle, test), e in final.items():
    per.setdefault(vehicle, {'PASSED': 0, 'FAILED': 0, 'failed': []})
    per[vehicle][e['result']] += 1
    if e['result'] == 'FAILED':
        per[vehicle]['failed'].append(test)
for vehicle, c in per.items():
    print(vehicle, 'final passed', c['PASSED'], 'final failed', c['FAILED'], c['failed'])
