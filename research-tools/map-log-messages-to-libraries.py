"""Which library or vehicle directory of the pinned ArduPilot snapshot writes each DataFlash message seen in simulated flights.

    python3 map-log-messages-to-libraries.py <ardupilot tree> <counts csv from analyze-dataflash-log.py> <out csv>

For every message name in the counts file the script searches the source for:
  - a self-describing write: Write("NAME", ...), WriteStreaming("NAME", ...), WriteCritical("NAME", ...) (the call that produces the message);
  - a declared structure: a LogStructure line holding "NAME" and a LOG_<X>_MSG id, then the places that use that id outside the LogStructure files.
Each hit is a (message, directory, file:line, kind) record. A message whose writes sit in exactly one library directory is credited to that library; one with several directories or
only in a vehicle directory is listed as shared. The match is a text search: it shows where the writing call is, and the log shows the call ran in the flight.
"""
import csv
import os
import re
import sys
from collections import Counter, defaultdict

tree, counts_csv, out = sys.argv[1], sys.argv[2], sys.argv[3]
SKIP_DIRS = {'modules', 'build', '.git', 'Tools', 'tests'}
SOURCE_EXT = ('.cpp', '.h', '.hpp')


def read_counts():
    totals = defaultdict(lambda: Counter())
    for row in csv.DictReader(open(counts_csv, encoding='utf-8')):
        totals[row['message']][row['log']] += int(row['count'])
    return totals


def source_files():
    for base in ('libraries', 'ArduCopter', 'ArduPlane', 'Rover', 'ArduSub', 'Blimp', 'AntennaTracker'):
        for root, dirs, files in os.walk(os.path.join(tree, base)):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if f.endswith(SOURCE_EXT):
                    yield os.path.join(root, f)


def directory_of(path):
    rel = os.path.relpath(path, tree).replace('\\', '/')
    parts = rel.split('/')
    return '/'.join(parts[:2]) if parts[0] == 'libraries' else parts[0]


def main():
    totals = read_counts()
    names = sorted(totals)
    files = list(source_files())
    texts = {}
    for p in files:
        try:
            texts[p] = open(p, encoding='utf-8', errors='replace').read().splitlines()
        except OSError:
            continue
    write_re = {n: re.compile(r'\b(?:Write|WriteStreaming|WriteCritical|WriteBlock)\w*\s*\(\s*"%s"' % re.escape(n)) for n in names}
    decl_re = {n: re.compile(r'"%s"' % re.escape(n)) for n in names}
    id_re = re.compile(r'\bLOG_[A-Z0-9_]+_MSG\b')
    hits = defaultdict(list)                 # message -> [(dir, 'file:line', kind)]
    ids = {}                                 # message -> LOG_X_MSG id
    for p, lines in texts.items():
        rel = os.path.relpath(p, tree).replace('\\', '/')
        for i, line in enumerate(lines, 1):
            for n in names:
                if write_re[n].search(line):
                    hits[n].append((directory_of(p), '%s:%d' % (rel, i), 'self-describing write'))
            if 'LogStructure' in rel or rel.endswith('LogStructure.h'):
                for n in names:
                    if decl_re[n].search(line):
                        m = id_re.search(' '.join(lines[max(0, i - 4):i + 1]))
                        if m:
                            ids[n] = m.group(0)
    for p, lines in texts.items():
        rel = os.path.relpath(p, tree).replace('\\', '/')
        if rel.endswith('LogStructure.h'):
            continue
        for i, line in enumerate(lines, 1):
            for n, ident in ids.items():
                if ident in line:
                    hits[n].append((directory_of(p), '%s:%d' % (rel, i), 'uses %s' % ident))
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['message', 'logs_and_counts', 'declared_id', 'credited_to', 'directories', 'first_sites'])
        for n in names:
            dirs = sorted({h[0] for h in hits[n]})
            libs = [d for d in dirs if d.startswith('libraries/')]
            credited = libs[0] if len(libs) == 1 and len(dirs) == 1 else ('shared' if hits[n] else 'not found in source')
            w.writerow([n, '; '.join('%s=%d' % kv for kv in sorted(totals[n].items())), ids.get(n, ''), credited, ' '.join(dirs), ' | '.join('%s [%s]' % (h[1], h[2]) for h in hits[n][:3])])
    print('%d messages mapped; credited to one library: %d' % (len(names), sum(1 for n in names if len({h[0] for h in hits[n]}) == 1 and any(h[0].startswith('libraries/') for h in hits[n]))))


if __name__ == '__main__':
    main()
