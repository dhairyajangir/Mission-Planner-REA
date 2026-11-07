"""Build coverage/matrix.csv: one row per Mission Planner / ArduPilot item with an evidence level.

Level (see coverage/README.md): L0 inventoried, L1 named in a trace, L2 binary type in REA index (automatic);
L3 tested in SITL (only via coverage/claims.csv, evidence files must exist). Independent flags: fault_injected
(yes when drops/corruption/resets were injected) and gui_kind (none | modified-copy | original).

    python research-tools/build-coverage-matrix.py          # rewrite coverage/matrix.csv and summary.md
    python research-tools/build-coverage-matrix.py --check  # fail if claims are invalid or matrix is stale
"""
import csv
import hashlib
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COV = ROOT / 'coverage'
MP = ROOT / 'mission-planner-1.3.83-source'
AP = ROOT / 'ardupilot-source/ardupilot-master'
TRACE_DOCS = [p for p in ROOT.glob('*.md') if p.name not in ('README.md', 'AGENTS.md', 'PHASE0-BASELINE.md', 'Reverse-Engineering-Coverage.md')]
FIELDS = ['row_id', 'area', 'item', 'source_ref', 'level', 'fault_injected', 'gui_kind', 'target', 'at_target',
          'status', 'evidence', 'evidence_sha12', 'note']
# Target = minimum level plus required flags: L3, +fault, +gui (original unmodified GUI).
TARGET = {'mp-page': 'L3+gui', 'mp-module': 'L3+gui', 'ledger': 'L3+fault', 'ap-lib': 'L3', 'ap-vehicle': 'L3', 'ap-mode': 'L3'}

# (item, source file/dir relative to the MP tree, REA type-name suffix or namespace prefix)
MP_MODULES = [
    ('FlightData', 'GCSViews/FlightData.cs', 'GCSViews.FlightData'),
    ('FlightPlanner', 'GCSViews/FlightPlanner.cs', 'GCSViews.FlightPlanner'),
    ('InitialSetup', 'GCSViews/InitialSetup.cs', 'GCSViews.InitialSetup'),
    ('SoftwareConfig', 'GCSViews/SoftwareConfig.cs', 'GCSViews.SoftwareConfig'),
    ('Help', 'GCSViews/Help.cs', 'GCSViews.Help'),
    ('SITL', 'GCSViews/SITL.cs', 'GCSViews.SITL'),
    ('MainV2', 'MainV2.cs', 'MainV2'),
    ('MagCalib', 'MagCalib.cs', 'MagCalib'),
] + [(d, d, 'MissionPlanner.' + d + '.') for d in
     ('Controls', 'Plugin', 'Grid', 'Joystick', 'Swarm', 'Antenna', 'Log', 'LogAnalyzer', 'Radio', 'SikRadio',
      'NoFly', 'Warnings', 'GeoRef', 'Updater', 'Utilities', 'Drivers', 'Plugins', 'Scripts')]


def sha12(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def doc_text():
    return '\n'.join(p.read_text(encoding='utf-8', errors='replace') for p in TRACE_DOCS)


def load_types():
    db = sqlite3.connect('file:' + (ROOT / 'mission-planner-binary-evidence/rea-main-index.sqlite').as_posix() + '?mode=ro', uri=True)
    try:
        return [r[0] for r in db.execute('SELECT full_name FROM types') if r[0]]
    finally:
        db.close()


def build_rows():
    docs, types = doc_text(), load_types()
    mentioned = lambda name: bool(re.search(r'(?<![A-Za-z0-9_])' + re.escape(name) + r'(?![A-Za-z0-9_])', docs))
    rows = []

    def add(row_id, area, item, source_ref, auto, note=''):
        rows.append({'row_id': row_id, 'area': area, 'item': item, 'source_ref': source_ref, 'auto_level': auto,
                     'note': note})

    with (ROOT / 'mission-planner-binary-evidence/configuration-page-source-inventory.csv').open(encoding='utf-8', newline='') as f:
        seen = set()
        for r in csv.DictReader(f):
            page = r['page_type']
            if page in seen:
                continue
            seen.add(page)
            auto = 0
            if mentioned(page):
                auto = 1
            if any(t.endswith('.' + page) for t in types):
                auto = max(auto, 2)
            add('mp-page:' + page, 'mp-page', page, f"{r['source_file']}:{r['line']}", auto)
    for item, src, tname in MP_MODULES:
        exists = (MP / src).exists()
        auto = 0 if exists else -1
        if exists and (mentioned(item) or mentioned(src)):
            auto = 1
        if exists and any((t.startswith(tname) if tname.endswith('.') else t.endswith(tname)) for t in types):
            auto = max(auto, 2)
        add('mp-module:' + item, 'mp-module', item, 'mission-planner-1.3.83-source/' + src, auto,
            '' if exists else 'source path not found')
    for d in sorted(p for p in (AP / 'libraries').iterdir() if p.is_dir()):
        add('ap-lib:' + d.name, 'ap-lib', d.name, 'ardupilot-source/ardupilot-master/libraries/' + d.name,
            1 if mentioned(d.name) else 0)
    for v in ('AntennaTracker', 'ArduCopter', 'ArduPlane', 'ArduSub', 'Blimp', 'Rover'):
        add('ap-vehicle:' + v, 'ap-vehicle', v, 'ardupilot-source/ardupilot-master/' + v, 1 if mentioned(v) else 0)
        for m in sorted(list((AP / v).glob('mode_*.cpp')) + list((AP / v).glob('control_*.cpp'))):
            camel = ''.join(w.capitalize() for w in re.split('_', m.stem))
            add(f'ap-mode:{v}/{m.stem}', 'ap-mode', f'{v} {m.stem}', f'ardupilot-source/ardupilot-master/{v}/{m.name}',
                1 if (mentioned(m.stem) or mentioned(camel)) else 0)
    return rows


def load_claims():
    path = COV / 'claims.csv'
    with path.open(encoding='utf-8', newline='') as f:
        return {r['row_id']: r for r in csv.DictReader(f)}


def merge(rows, claims):
    problems = []
    ids = {r['row_id'] for r in rows}
    for cid in claims:
        if cid not in ids and not cid.startswith('ledger:'):
            problems.append(f'claim for unknown row {cid}')
    for cid, c in claims.items():
        if cid.startswith('ledger:'):
            rows.append({'row_id': cid, 'area': 'ledger', 'item': cid[7:], 'source_ref': 'Reverse-Engineering-Coverage.md',
                         'auto_level': 1, 'note': ''})
    for r in rows:
        c = claims.get(r['row_id'])
        paths = [p for p in (c['evidence'].split(';') if c else []) if p]
        claimed = int(c['level']) if c else 0
        for p in paths:
            if not (ROOT / p).is_file():
                problems.append(f"{r['row_id']}: evidence file missing: {p}")
        if claimed >= 3 and not paths:
            problems.append(f"{r['row_id']}: level {claimed} claimed without evidence")
        fault, gui = (c['fault_injected'], c['gui_kind']) if c else ('', '')
        if claimed > 3 or fault not in ('', 'yes') or gui not in ('', 'none', 'modified-copy', 'original'):
            problems.append(f"{r['row_id']}: bad level/fault/gui values")
        if (fault == 'yes' or gui == 'original') and claimed < 3:
            problems.append(f"{r['row_id']}: fault/original-GUI claim needs level 3")
        r['level'] = max(r['auto_level'], claimed)
        r['fault_injected'] = fault
        r['gui_kind'] = gui
        r['target'] = (c.get('target') if c and c.get('target') else TARGET[r['area']])
        need = r['target']
        r['at_target'] = 'yes' if (r['level'] >= 3 and ('+fault' not in need or fault == 'yes')
                                  and ('+gui' not in need or gui == 'original')) else ''
        r['status'] = c['status'] if c else ''
        r['evidence'] = ';'.join(paths)
        r['evidence_sha12'] = ';'.join(sha12(ROOT / p) for p in paths if (ROOT / p).is_file())
        if c and c.get('note'):
            r['note'] = (r['note'] + ' ' + c['note']).strip()
    return rows, problems


def summary(rows):
    lines = ['# Coverage summary', '', 'Generated by `research-tools/build-coverage-matrix.py`. Do not edit.', '',
             '| Area | Rows | L0 | L1 | L2 | L3 | + fault-injected | + original GUI | At target |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for area in TARGET:
        sel = [r for r in rows if r['area'] == area]
        c = Counter(r['level'] for r in sel)
        hit = sum(1 for r in sel if r['at_target'])
        fault = sum(1 for r in sel if r['fault_injected'])
        gui = sum(1 for r in sel if r['gui_kind'] == 'original')
        lines.append(f"| {area} | {len(sel)} | " + ' | '.join(str(c.get(i, 0)) for i in range(4)) + f' | {fault} | {gui} | {hit} |')
    lines += ['', 'Level = highest evidence kind reached for a row, not breadth; a modified-copy GUI does not count as original GUI. `status` and `note` in matrix.csv say how partial.']
    return '\n'.join(lines) + '\n'


def render(rows):
    import io
    buf = io.StringIO(newline='')
    w = csv.DictWriter(buf, FIELDS, lineterminator='\n', extrasaction='ignore')
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def main():
    rows, problems = merge(build_rows(), load_claims())
    text, summ = render(rows), summary(rows)
    if problems:
        print('\n'.join('PROBLEM ' + p for p in problems))
        raise SystemExit(1)
    m, s = COV / 'matrix.csv', COV / 'summary.md'
    if '--check' in sys.argv:
        stale = [p.name for p, t in ((m, text), (s, summ)) if not p.exists() or p.read_text(encoding='utf-8') != t]
        if stale:
            print('STALE ' + ', '.join(stale) + ' (re-run without --check)')
            raise SystemExit(1)
        print(f'OK {len(rows)} rows, claims valid, matrix current')
        return
    m.write_text(text, encoding='utf-8', newline='\n')
    s.write_text(summ, encoding='utf-8', newline='\n')
    print(f'wrote {len(rows)} rows')
    print(summ)


if __name__ == '__main__':
    main()
