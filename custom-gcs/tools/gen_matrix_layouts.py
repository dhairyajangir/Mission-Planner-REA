"""Generate customgcs/data/matrix_layouts.json from AP_MotorsMatrix.cpp and AP_Motors_Class.h of a supplied ArduPilot tree.

For every (frame class, frame type) the file lists the motors: motor number (1 based, equal to the servo function offset), testing order and rotation (CW/CCW or "?"),
as the firmware's own tables define them. The tricopter (class 7) is not a matrix class; its test sequence is added by hand from AP_MotorsTri::_output_test_seq.

    python gen_matrix_layouts.py <ardupilot tree> <out json>
"""
import json
import os
import re
import sys

tree, out = sys.argv[1:3]
MATRIX_CLASS = {'quad': 1, 'hexa': 2, 'octa': 3, 'octaquad': 4, 'y6': 5, 'dodecahexa': 12, 'deca': 14}
YAW = {'AP_MOTORS_MATRIX_YAW_FACTOR_CW': 'CW', 'AP_MOTORS_MATRIX_YAW_FACTOR_CCW': 'CCW'}
header = open(os.path.join(tree, 'libraries/AP_Motors/AP_Motors_Class.h'), encoding='utf-8').read()
enums = {m.group(1): int(m.group(2)) for m in re.finditer(r'(MOTOR_FRAME_(?:TYPE_)?[A-Z0-9_]+)\s*=\s*(\d+)', header)}
src = open(os.path.join(tree, 'libraries/AP_Motors/AP_MotorsMatrix.cpp'), encoding='utf-8').read()


def rotation(token):
    token = token.strip()
    if token in YAW:
        return YAW[token]
    try:
        v = float(token.rstrip('f'))
    except ValueError:
        return '?'
    return 'CCW' if v > 0 else 'CW' if v < 0 else '?'


def table(block):
    rows = []
    for i, e in enumerate(re.findall(r'\{([^{}]*)\}', block)):
        parts = [p.strip() for p in e.split(',')]
        rows.append({'number': i + 1, 'order': int(re.sub(r'\D', '', parts[-1])), 'rotation': rotation(parts[-2])})
    return rows


layouts = {}
for fm in re.finditer(r'bool AP_MotorsMatrix::setup_(\w+?)_matrix\(motor_frame_type frame_type\)\s*\{', src):
    cls = MATRIX_CLASS.get(fm.group(1))
    if cls is None:
        continue
    end = src.find('\nbool AP_MotorsMatrix::', fm.end())
    body = re.sub(r'//[^\n]*', '', src[fm.end(): end if end > 0 else len(src)])
    labels, pending, last = [], {}, None

    def flush():
        if pending:
            for lab in labels:
                layouts['%d:%s' % (cls, 'default' if lab is None else lab)] = [dict(number=n, order=o, rotation=r) for n, (o, r) in sorted(pending.items())]

    for tok in re.finditer(r'case (MOTOR_FRAME_TYPE_[A-Z0-9_]+):|default:|static const AP_MotorsMatrix::MotorDef(?:Raw)? motors\[\]\s*\{(.*?)\};|add_motor\(AP_MOTORS_MOT_(\d+),([^;]*)\);', body, re.S):
        text = tok.group(0)
        if tok.group(1) or text.startswith('default'):
            if last != 'label':
                flush()
                labels, pending = [], {}
            labels.append(enums[tok.group(1)] if tok.group(1) else None)
            last = 'label'
        elif tok.group(3):
            args = [a.strip() for a in tok.group(4).split(',')]
            pending[int(tok.group(3))] = (int(re.sub(r'\D', '', args[-1])), rotation(args[-2]))
            last = 'add'
        else:
            for lab in labels:
                layouts['%d:%s' % (cls, 'default' if lab is None else lab)] = table(tok.group(2))
            labels, pending, last = [], {}, 'table'
    flush()
# tricopter, by hand from AP_MotorsTri::_output_test_seq: sequence 1 motor 1, 2 motor 4, 3 tail servo (output 7), 4 motor 2; PLUSREV (6): motor 4, tail, motor 1, motor 2
layouts['7:default'] = [dict(number=1, order=1, rotation='?'), dict(number=4, order=2, rotation='?'), dict(number=7, order=3, rotation='?'), dict(number=2, order=4, rotation='?')]
layouts['7:6'] = [dict(number=4, order=1, rotation='?'), dict(number=7, order=2, rotation='?'), dict(number=1, order=3, rotation='?'), dict(number=2, order=4, rotation='?')]
json.dump({'source': 'AP_MotorsMatrix.cpp and AP_Motors_Class.h of the supplied tree; class 7 by hand from AP_MotorsTri.cpp', 'layouts': layouts}, open(out, 'w'), indent=1, sort_keys=True)
print(len(layouts), 'layouts')
