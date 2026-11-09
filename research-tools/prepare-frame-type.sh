#!/bin/bash
# usage: prepare-frame-type.sh <simulator model> <FRAME_TYPE> <work dir name under ~>
# Starts a disposable ArduCopter SITL of the model, sets FRAME_TYPE, stops it and leaves ~/<work dir name> with the stored parameters (eeprom.bin), so the
# simulator can be started again from it without wiping. Uses the preparation step of sitl-frame-motor-sweep.py. Simulator only.
source ~/venv-ap/bin/activate
python3 - "$1" "$2" "$3" <<'PY'
import os
import sys
model, ftype, work = sys.argv[1], sys.argv[2], os.path.expanduser('~/' + sys.argv[3])
sys.argv = ['x', os.path.expanduser('~/ap-snapshot'), os.path.expanduser('~/prepare-out')]
src = open(os.path.expanduser('~/sitl-frame-motor-sweep.py')).read().replace('\nmain()\n', '\n')
exec(compile(src, 'sweep', 'exec'))
print('prepared:', prepare(model, work, {'FRAME_TYPE': float(ftype)}), 'work dir', work)
PY
