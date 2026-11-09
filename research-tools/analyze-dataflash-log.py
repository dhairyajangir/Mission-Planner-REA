"""Count the message types in ArduPilot DataFlash logs (.BIN or .BIN.gz) with pymavlink's own reader, per log, and write a CSV.

    python3 analyze-dataflash-log.py <out csv> <log> [<log> ...]

Columns: log, message, count, fields (the format's column names). Meant to be run in the WSL environment that has pymavlink. It only counts what the vehicle wrote; it says nothing
about whether a message is correct. Used to show which library's logging code ran in a simulated flight (see map-log-messages-to-libraries.py).
"""
import csv
import gzip
import os
import shutil
import sys
import tempfile
from collections import Counter

from pymavlink import DFReader

out = sys.argv[1]
rows = []
for path in sys.argv[2:]:
    source = path
    tmp = None
    if path.endswith('.gz'):
        tmp = tempfile.NamedTemporaryFile(suffix='.BIN', delete=False)
        with gzip.open(path, 'rb') as src:
            shutil.copyfileobj(src, tmp)
        tmp.close()
        source = tmp.name
    log = DFReader.DFReader_binary(source)
    counts, fields = Counter(), {}
    while True:
        m = log.recv_match()
        if m is None:
            break
        name = m.get_type()
        counts[name] += 1
        if name not in fields:
            fields[name] = ' '.join(m.get_fieldnames())
    for name in sorted(counts):
        rows.append([os.path.basename(path), name, counts[name], fields[name]])
    print('%s: %d message types, %d messages' % (os.path.basename(path), len(counts), sum(counts.values())))
    if tmp:
        os.unlink(tmp.name)
with open(out, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['log', 'message', 'count', 'fields'])
    w.writerows(rows)
