"""Compare what the original ConfigMotorTest page drew for a frame (sitl-evidence/motor-layout-page/layout-<label>.txt: the "Motor Number" label next to each
"Test motor <letter>" button, in button order) with the servo output that actually moved for the same sequence number in the motor test sweep
(sitl-evidence/frame-motor-sweep/frame-sweep-sequences.csv, run on the same frame model).

    python compare-page-labels-with-sweep.py <motor-layout-page dir> <frame-sweep-sequences.csv> <out csv>
"""
import csv
import os
import re
import sys

page_dir, sweep_csv, out_csv = sys.argv[1:4]
# page probe label -> frame name used by the sweep (same simulator model)
PAIRS = [('quad-plus', 'quad'), ('quad-x', 'X'), ('quad-bfx', 'bfx'), ('hexa', 'hexa'), ('hexa-x', 'hexax'), ('octa', 'octa'), ('octa-quad', 'octa-quad'),
         ('y6', 'y6'), ('tri', 'tri'), ('deca', 'deca'), ('dodeca-hexa', 'dodeca-hexa'), ('singlecopter', 'singlecopter'), ('coaxcopter', 'coaxcopter'), ('heli', None)]
sweep = {}
for r in csv.DictReader(open(sweep_csv, newline='')):
    sweep.setdefault(r['frame'], []).append((int(r['sequence']), r['observed_servos_moved_20us_or_more']))
rows = []
for label, frame in PAIRS:
    text = open(os.path.join(page_dir, 'layout-%s.txt' % label), encoding='utf-8').read().splitlines()
    buttons = [l for l in text if re.search(r'BUTTON .*text=Test motor ', l)]
    labels = [re.search(r'text=Motor Number: (\d+)', l).group(1) for l in text if 'LABEL' in l and 'Motor Number:' in l]
    cls = typ = '?'
    for l in text:
        if ' TEXT FrameClass = ' in l:
            cls = l.split(' = ', 1)[1]
        if ' TEXT FrameType = ' in l:
            typ = l.split(' = ', 1)[1]
    moved = [m for _, m in sorted(sweep.get(frame, []))]
    n_vehicle = len(moved)
    if frame is None:
        verdict = 'page draws no motor buttons (motor count 0); no sweep run on the vehicle for this frame'
    elif not labels:
        verdict = 'page draws %d buttons and no labels; vehicle has %d test sequences' % (len(buttons), n_vehicle)
    elif labels == moved:
        verdict = 'labels match the servos that moved, in order'
    else:
        verdict = 'MISMATCH'
    rows.append([label, cls, typ, len(buttons), ' '.join(labels), ' '.join(moved), verdict])
with open(out_csv, 'w', newline='') as f:
    w = csv.writer(f, lineterminator='\n')
    w.writerow(['frame', 'page_class_text', 'page_type_text', 'buttons_drawn', 'page_motor_numbers_in_button_order', 'servos_that_moved_in_sequence_order', 'verdict'])
    w.writerows(rows)
for r in rows:
    print(r)
