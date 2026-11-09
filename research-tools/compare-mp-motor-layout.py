"""Compare Mission Planner 1.3.83's APMotorLayout.json (what the motor test page labels its buttons from) with the motor tables in the supplied
ArduPilot source (libraries/AP_Motors/AP_MotorsMatrix.cpp). Static comparison, no simulator.

For every (FRAME_CLASS, FRAME_TYPE) in the JSON the page shows button "Test motor <letter for test order n>" with the label "Motor Number: <Number>, <Rotation>".
The vehicle's table gives, for the motor at servo output i+1, its testing_order and yaw factor (CCW = 1, CW = -1 in AP_MotorsMatrix). This script reports,
per combination, whether the JSON and the source agree on motor count, number-by-test-order and rotation, and which combinations only one side has.

    python compare-mp-motor-layout.py <APMotorLayout.json> <AP_MotorsMatrix.cpp> <AP_Motors_Class.h> <out csv>
"""
import csv
import json
import re
import sys

layout_path, matrix_path, header_path, out_path = sys.argv[1:5]
MATRIX_CLASS = {'quad': 1, 'hexa': 2, 'octa': 3, 'octaquad': 4, 'y6': 5, 'dodecahexa': 12, 'deca': 14}
header = open(header_path, encoding='utf-8').read()
enums = {m.group(1): int(m.group(2)) for m in re.finditer(r'(MOTOR_FRAME_(?:TYPE_)?[A-Z0-9_]+)\s*=\s*(\d+)', header)}
src = open(matrix_path, encoding='utf-8').read()
YAW = {'AP_MOTORS_MATRIX_YAW_FACTOR_CW': 'CW', 'AP_MOTORS_MATRIX_YAW_FACTOR_CCW': 'CCW'}


def rotation(token):
    """CW/CCW from a yaw-factor token: the named constants, or the sign of a number (CCW = +1, CW = -1 in AP_MotorsMatrix); 0 = no yaw = '?'."""
    token = token.strip()
    if token in YAW:
        return YAW[token]
    try:
        v = float(token.rstrip('f'))
    except ValueError:
        return '?'
    return 'CCW' if v > 0 else 'CW' if v < 0 else '?'


def entries(block):
    """[(testing_order, rotation or '?')] in motor-index order for one table body."""
    out = []
    for e in re.findall(r'\{([^{}]*)\}', block):
        parts = [p.strip() for p in e.split(',')]
        order = int(re.sub(r'\D', '', parts[-1]))
        out.append((order, rotation(parts[-2])))       # yaw factor is the second-to-last field in both MotorDef and MotorDefRaw
    return out


source = {}
for fm in re.finditer(r'bool AP_MotorsMatrix::setup_(\w+?)_matrix\(motor_frame_type frame_type\)\s*\{', src):
    cls = MATRIX_CLASS.get(fm.group(1))
    if cls is None:
        continue
    end = src.find('\nbool AP_MotorsMatrix::', fm.end())
    body = src[fm.end(): end if end > 0 else len(src)]
    labels, pending, last = [], {}, None

    def flush():
        """add_motor-style cases (V-tail, A-tail): store the collected calls under the case labels that preceded them."""
        if pending:
            for lab in labels:
                source[(cls, lab)] = [pending[n] for n in sorted(pending)]

    # tokens in file order: case labels, static tables and add_motor(...) calls; a case label that follows anything but another label starts a new case
    for tok in re.finditer(r'case (MOTOR_FRAME_TYPE_[A-Z0-9_]+):|default:|static const AP_MotorsMatrix::MotorDef(?:Raw)? motors\[\]\s*\{(.*?)\};|add_motor\(AP_MOTORS_MOT_(\d+),([^;]*)\);', body, re.S):
        text = tok.group(0)
        if tok.group(1) or text.startswith('default'):
            if last != 'label':
                flush()
                labels, pending = [], {}
            labels.append(enums[tok.group(1)] if tok.group(1) else None)
            last = 'label'
        elif tok.group(3):
            args = [x.strip() for x in tok.group(4).split(',')]
            pending[int(tok.group(3))] = (int(re.sub(r'\D', '', args[-1])), rotation(args[-2]))
            last = 'add'
        else:
            for lab in labels:
                source[(cls, lab)] = entries(tok.group(2))
            labels, pending, last = [], {}, 'table'
    flush()

data = json.load(open(layout_path, encoding='utf-8'))
rows = []
seen = set()
for lay in data['layouts']:
    key = (lay['Class'], lay['Type'])
    seen.add(key)
    mp = {m['TestOrder']: (m['Number'], m['Rotation']) for m in lay['motors']}
    table = source.get(key) or (source.get((key[0], None)) if key[0] == 5 else None)
    if table is None:
        rows.append([key[0], key[1], len(mp), 'n/a', 'JSON only (no matrix table for this combination)', '', ''])
        continue
    src_by_order = {o: (i + 1, r) for i, (o, r) in enumerate(table)}
    diffs_num = [o for o in sorted(set(mp) | set(src_by_order)) if mp.get(o, (None,))[0] != src_by_order.get(o, (None,))[0]]
    diffs_rot = [o for o in sorted(set(mp) & set(src_by_order)) if mp[o][1] not in ('?', src_by_order[o][1])]
    verdict = 'agree' if not diffs_num and not diffs_rot and len(mp) == len(table) else 'DIFFER'
    rows.append([key[0], key[1], len(mp), len(table), verdict, ' '.join(map(str, diffs_num)), ' '.join(map(str, diffs_rot))])
for key in sorted(k for k in source if k[1] is not None and k not in seen):
    rows.append([key[0], key[1], 'n/a', len(source[key]), 'source only (page falls back to its MAV_TYPE guess)', '', ''])
# tricopter: the JSON has 19 class-7 entries; the matrix source has none (AP_MotorsTri is a separate class). Compare each with the test sequence transcribed BY HAND from
# AP_MotorsTri::_output_test_seq: sequence 1..4 drives servo outputs 1, 4, 7 (tail servo), 2, or 4, 7, 1, 2 when FRAME_TYPE is PLUSREV (6, "pitch reversed").
TRI_SEQ = {False: [1, 4, 7, 2], True: [4, 7, 1, 2]}
tri_bad = []
tri_n = 0
for lay in data['layouts']:
    if lay['Class'] != 7:
        continue
    tri_n += 1
    got = [n for _, n in sorted((m['TestOrder'], m['Number']) for m in lay['motors'])]
    if got != TRI_SEQ[lay['Type'] == 6]:
        tri_bad.append((lay['Type'], got))
print('tri entries:', tri_n, 'matching the hand-transcribed AP_MotorsTri sequence:', tri_n - len(tri_bad), 'not matching:', tri_bad)
with open(out_path, 'w', newline='') as f:
    w = csv.writer(f, lineterminator='\n')
    w.writerow(['frame_class', 'frame_type', 'json_motors', 'source_motors', 'verdict', 'test_orders_with_different_motor_number', 'test_orders_with_different_rotation'])
    w.writerows(rows)
tot = len(rows)
print('combinations:', tot, 'agree:', sum(r[4] == 'agree' for r in rows), 'differ:', sum(r[4] == 'DIFFER' for r in rows),
      'json only:', sum(r[4].startswith('JSON only') for r in rows), 'source only:', sum(r[4].startswith('source only') for r in rows))
for r in rows:
    if r[4] != 'agree':
        print(r)
