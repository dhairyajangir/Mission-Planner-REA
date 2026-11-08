"""Append the PageStateProbe results (sitl-evidence/page-state/page-state.csv) to the matching mp-page rows in coverage/claims.csv,
add one ledger row, and add the matching row to Reverse-Engineering-Coverage.md. Safe to run once; rows that already mention the
evidence file are skipped.
"""
import csv
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, 'sitl-evidence', 'page-state', 'page-state.csv')
CLAIMS = os.path.join(ROOT, 'coverage', 'claims.csv')
LEDGER = os.path.join(ROOT, 'Reverse-Engineering-Coverage.md')
EVID = ('sitl-evidence/page-state/page-state.csv;sitl-evidence/page-state/message-boxes.txt;sitl-evidence/page-state/console.txt;'
        'research-tools/PageStateProbe.cs;research-tools/run-page-state-probe.ps1;Setup-Page-State-Trace.md')

KNOWN = {
    'ConfigFrameType': " Source reading: Activate() disables the page when the legacy FRAME parameter is absent (ConfigFrameType.cs); this Copter exposes FRAME_CLASS and FRAME_TYPE, and ConfigFrameClassType is the enabled one.",
    'ConfigArduplane': " Disabled on a Copter, as expected for a vehicle-specific page (reason not examined in source).",
    'ConfigArdurover': " Disabled on a Copter, as expected for a vehicle-specific page (reason not examined in source).",
    'ConfigAntennaTracker': " Disabled on a Copter, as expected for a vehicle-specific page (reason not examined in source).",
    'ConfigSimplePids': " The exception is a missing data file (acsimplepids.xml is looked up beside the harness executable, not the Mission Planner folder), so it is a harness limitation.",
}

rows = list(csv.DictReader(open(RES, newline='')))
by = {r['page']: r for r in rows}


def note(r):
    base = ("Copter-connected state (probe harness, not a person: MainV2.comPort connected to a disposable Copter SITL with 1,431 parameters, Activate() called, events pumped): status %s, enabled=%s, "
            "%s of %s interactive controls enabled, %s message box(es) raised (logged and answered Yes by the harness)." % (r['status'], r['enabled'], r['interactive_enabled'], r['interactive_total'], r['message_boxes']))
    if r['status'] == 'exception':
        base += (" Exception: %s. The harness runs without the full application, so this is not evidence the page is broken; cause not examined." % r['detail'])
    if r['status'] == 'timeout':
        base += " Did not finish within 20 s; cause not examined."
    if r['enabled'] == 'False' and r['status'] == 'ok':
        base += " The page ended up disabled."
    return base + KNOWN.get(r['page'], '')


lines = open(CLAIMS, 'rb').read().decode('utf-8').split('\n')
out, changed = [], 0
for line in lines:
    key = line.split(',', 1)[0]
    if key.startswith('mp-page:') and key[8:] in by and 'page-state.csv' not in line:
        f = next(csv.reader([line]))
        f[6] = f[6] + ';' + EVID
        f[7] = f[7].rstrip() + ' ' + note(by[key[8:]])
        buf = io.StringIO()
        csv.writer(buf, lineterminator='').writerow(f)
        line = buf.getvalue()
        changed += 1
    out.append(line)
s = '\n'.join(out)
if not s.endswith('\n'):
    s += '\n'
n_ok = sum(1 for r in rows if r['status'] == 'ok')
n_dis = sum(1 for r in rows if r['status'] == 'ok' and r['enabled'] == 'False')
n_exc = sum(1 for r in rows if r['status'] == 'exception')
n_to = sum(1 for r in rows if r['status'] == 'timeout')
ledger_note = ("A probe harness (not a person) activated %d original Mission Planner setup pages against a disposable Copter SITL: %d ran and ended enabled, %d ended disabled (for example ConfigFrameType, which needs the legacy FRAME parameter; "
               "ConfigFrameClassType is the enabled one), %d threw exceptions (harness limits suspected, not examined) and %d timed out. Enabled/disabled and control counts only; no page behaviour beyond the earlier flight-modes, failsafe and tuning checks."
               % (len(rows), n_ok - n_dis, n_dis, n_exc, n_to))
if 'ledger:setup-page-state-copter' not in s:
    s += 'ledger:setup-page-state-copter,3,,modified-copy,,partial,' + EVID + ',"' + ledger_note.replace('"', "'") + '"\n'
open(CLAIMS, 'wb').write(s.encode('utf-8'))
print('claims rows changed:', changed, '| ok enabled', n_ok - n_dis, 'disabled', n_dis, 'exceptions', n_exc, 'timeouts', n_to)

raw = open(LEDGER, 'rb').read().decode('utf-8')
ls = raw.split('\n')
for i, l in enumerate(ls):
    if l.lstrip('\r').startswith('| ArduPilot libraries named in autotests |'):
        eol = '\r' if l.endswith('\r') else ''
        new = ('| Setup page state against a Copter SITL | Partial | `research-tools/PageStateProbe.cs` activated %d original Mission Planner setup pages (harness, not a person) with `MainV2.comPort` connected to a disposable Copter SITL: '
               '%d ran and ended enabled, %d ended disabled (for example `ConfigFrameType`, which requires the legacy `FRAME` parameter; the Copter exposes `FRAME_CLASS`/`FRAME_TYPE` and `ConfigFrameClassType` is enabled), %d threw exceptions '
               '(the harness runs without the full application; not examined) and %d timed out. Enabled state and control counts only. Evidence in `sitl-evidence/page-state/`, trace in `Setup-Page-State-Trace.md`. |'
               % (len(rows), n_ok - n_dis, n_dis, n_exc, n_to)) + eol
        if 'Setup page state against a Copter SITL' not in raw:
            ls.insert(i + 1, new)
        break
open(LEDGER, 'wb').write('\n'.join(ls).encode('utf-8'))
print('ledger ok')
