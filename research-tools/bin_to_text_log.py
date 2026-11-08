"""Convert an ArduPilot DataFlash .BIN into the text .log form (FMT, ... / NAME, v1, v2, ...) that the old LogAnalyzer reads.
Run in WSL with pymavlink. Values are written with Python's default formatting; this is a test converter, not Mission
Planner's own (see research-tools/MissionPlannerLogConvertProbe.cs for that one).

    python bin_to_text_log.py <in.BIN> <out.log>
"""
import sys

from pymavlink import DFReader

log = DFReader.DFReader_binary(sys.argv[1], zero_time_base=True)
out = open(sys.argv[2], 'w')
for fmt in sorted(log.formats.values(), key=lambda f: f.type):
    out.write('FMT, %d, %d, %s, %s, %s\n' % (fmt.type, fmt.len, fmt.name, fmt.format, ','.join(fmt.columns)))
count = 0
while True:
    m = log.recv_match()
    if m is None:
        break
    if m.get_type() == 'FMT':
        continue
    vals = []
    for c in m.fmt.columns:
        v = getattr(m, c)
        if isinstance(v, bytes):
            v = v.decode('ascii', 'replace').rstrip('\x00')
        vals.append(str(v))
    out.write('%s, %s\n' % (m.get_type(), ', '.join(vals)))
    count += 1
out.close()
print('messages written:', count)
