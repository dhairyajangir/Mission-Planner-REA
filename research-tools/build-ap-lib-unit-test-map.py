"""Map ArduPilot libraries to the unit-test binaries built from libraries/<lib>/tests/ (waf "tests" target, board linux) and the results of running them
(sitl-evidence/unit-tests/: results.csv, binary-sources.csv, logs/). Counts the gtest cases each binary reported. Writes coverage/ap-lib-unit-tests.csv and, with --apply,
adds claims rows for libraries that are below level 3 in the matrix.

    python build-ap-lib-unit-test-map.py [--apply]
"""
import collections
import csv
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UT = os.path.join(ROOT, 'sitl-evidence', 'unit-tests')
OUT = os.path.join(ROOT, 'coverage', 'ap-lib-unit-tests.csv')
CLAIMS = os.path.join(ROOT, 'coverage', 'claims.csv')
MATRIX = os.path.join(ROOT, 'coverage', 'matrix.csv')

exit_code = {r['binary']: int(r['exit_code']) for r in csv.DictReader(open(os.path.join(UT, 'results.csv')))}
libs = collections.OrderedDict()
for row in csv.reader(open(os.path.join(UT, 'binary-sources.csv'))):
    name, src = row[0], row[1]
    if src:
        libs.setdefault(src.split('/')[1], []).append(name)


def cases(binary):
    text = open(os.path.join(UT, 'logs', binary + '.log'), encoding='utf-8', errors='replace').read()
    m = re.search(r'\[==========\] (\d+) tests? from', text)
    p = re.search(r'\[  PASSED  \] (\d+) tests?', text)
    return (int(m.group(1)) if m else None), (int(p.group(1)) if p else None)


level = {r['row_id'].split(':', 1)[1]: r['level'] for r in csv.DictReader(open(MATRIX, encoding='utf-8')) if r['area'] == 'ap-lib'}
rows = []
for lib, bins in libs.items():
    total = passed = 0
    unknown = []
    for b in bins:
        t, p = cases(b)
        if t is None:
            unknown.append(b)
            continue
        total += t
        passed += p or 0
    rows.append({'library': lib, 'level_before': level.get(lib, 'not in matrix'), 'binaries': len(bins), 'binaries_exit_0': sum(exit_code[b] == 0 for b in bins),
                 'gtest_cases': total, 'gtest_cases_passed': passed, 'binaries_without_gtest_summary': ' '.join(unknown), 'binary_names': ' '.join(bins)})
with open(OUT, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, list(rows[0].keys()), lineterminator='\n')
    w.writeheader()
    w.writerows(rows)
for r in rows:
    print('%-18s before=L%-3s binaries=%2d exit0=%2d cases=%3d passed=%3d %s' % (r['library'], r['level_before'], r['binaries'], r['binaries_exit_0'], r['gtest_cases'], r['gtest_cases_passed'], r['binaries_without_gtest_summary']))
if '--apply' in sys.argv:
    text = open(CLAIMS, 'rb').read().decode('utf-8')
    existing = {l.split(',', 1)[0] for l in text.split('\n') if l}
    if not text.endswith('\n'):
        text += '\n'
    added = 0
    for r in rows:
        key = 'ap-lib:' + r['library']
        if r['library'] not in level or level[r['library']] == '3' or key in existing:
            continue
        note = ("ArduPilot's own C++ unit tests (waf tests, board linux, pinned snapshot, run on this machine): %d test binar%s built from libraries/%s/tests, %d of %d exit 0, %d gtest cases, %d passed. "
                "Unit tests of the library's own code, not simulator flight; see coverage/ap-lib-unit-tests.csv."
                % (r['binaries'], 'y' if r['binaries'] == 1 else 'ies', r['library'], r['binaries_exit_0'], r['binaries'], r['gtest_cases'], r['gtest_cases_passed']))
        buf = io.StringIO()
        csv.writer(buf, lineterminator='').writerow([key, '3', '', 'none', '', 'partial', 'coverage/ap-lib-unit-tests.csv;sitl-evidence/unit-tests/results.csv;sitl-evidence/unit-tests/binary-sources.csv', note])
        text += buf.getvalue() + '\n'
        added += 1
    open(CLAIMS, 'wb').write(text.encode('utf-8'))
    print('claims rows added:', added)
