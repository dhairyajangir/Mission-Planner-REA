"""Extract the vehicle's own clock for events from a dataflash .BIN: MSG (status texts) and MODE rows with TimeUS, plus QTUN/VFR-style rows is not needed.
The GCS-side timestamps in sitl-quadplane-vtol-failsafe.py come from message arrival; this gives the vehicle-side times to cross-check them.

    python3 sitl-quadplane-vtol-failsafe-dflog.py <log.BIN> <out.txt>
Times are seconds since the first row of the log (boot); the line 'ARM' marks the first armed row if one is found (STAT/ARM message or the 'Arming' MSG).
"""
import sys

from pymavlink import DFReader

src, dst = sys.argv[1], sys.argv[2]
log = DFReader.DFReader_binary(src)
rows, t0 = [], None
while True:
    m = log.recv_match(type=['MSG', 'MODE'])
    if m is None:
        break
    us = getattr(m, 'TimeUS', 0)
    if t0 is None:
        t0 = us
    t = (us - t0) / 1e6
    if m.get_type() == 'MSG':
        rows.append('%9.3f MSG  %s' % (t, m.Message))
    else:
        rows.append('%9.3f MODE mode=%s modenum=%s reason=%s' % (t, getattr(m, 'Mode', '?'), getattr(m, 'ModeNum', '?'), getattr(m, 'Rsn', '?')))
open(dst, 'w').write('\n'.join(rows) + '\n')
print('%d rows -> %s' % (len(rows), dst))
