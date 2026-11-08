"""Append the second PageControlsProbe run (sitl-evidence/page-controls-2/) to the matching mp-page rows in coverage/claims.csv,
add a ledger row to claims.csv, and the matching row to Reverse-Engineering-Coverage.md plus a section in Setup-Page-Actions-Trace.md.
Run once; rows that already mention the evidence folder are skipped.
"""
import csv
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, 'sitl-evidence', 'page-controls-2')
CLAIMS = os.path.join(ROOT, 'coverage', 'claims.csv')
LEDGER = os.path.join(ROOT, 'Reverse-Engineering-Coverage.md')
TRACE = os.path.join(ROOT, 'Setup-Page-Actions-Trace.md')
EVID = ('sitl-evidence/page-controls-2/page-controls.csv;sitl-evidence/page-controls-2/page-controls-summary.csv;sitl-evidence/page-controls-2/message-boxes.txt;'
        'sitl-evidence/page-controls-2/console.txt;research-tools/PageControlsProbe.cs;research-tools/run-page-controls-probe.ps1;Setup-Page-Actions-Trace.md')

summ = list(csv.DictReader(open(os.path.join(D, 'page-controls-summary.csv'), newline='')))
detail = list(csv.DictReader(open(os.path.join(D, 'page-controls.csv'), newline='')))
EXTRA = {
    'ConfigAC_Fence': " The page raised one message box ('Set FENCE_ENABLE Failed') although the read-back shows both writes reached the vehicle (set to 1, then restored to 0); the check box's callback re-downloads the parameter list (ConfigAC_Fence.cs line 21), cause of the message not examined.",
    'ConfigTradHeli4': " This is the traditional-helicopter page; it was driven against the Copter (multirotor) simulator, so these writes show the controls work, not that the values suit a helicopter.",
}


def note(s):
    n_chg, c_chg = int(s['numeric_changed']), int(s['checkbox_changed'])
    if s['status'] != 'ok':
        return "Parameter-bound controls (probe harness, Copter SITL): page status %s %s." % (s['status'], s['detail'])
    if n_chg + c_chg == 0:
        return ("Parameter-bound controls (probe harness, Copter SITL): no numeric or check-box controls bound to a parameter on this vehicle were found, so nothing was changed "
                "(the page uses other write paths, or only combo boxes: %s listed, not changed)." % s['combo_listed'])
    return ("Parameter-bound controls (probe harness, not a person, Copter SITL): %d numeric and %d check-box controls changed by one step; %d and %d reached the vehicle (read back with GetParam) and %d and %d were restored; "
            "%s combo boxes listed, not changed.%s" % (n_chg, c_chg, int(s['numeric_applied']), int(s['checkbox_applied']), int(s['numeric_restored']), int(s['checkbox_restored']), s['combo_listed'], EXTRA.get(s['page'], '')))


by = {s['page']: s for s in summ}
lines = open(CLAIMS, 'rb').read().decode('utf-8').split('\n')
out, changed = [], 0
for line in lines:
    key = line.split(',', 1)[0]
    if key.startswith('mp-page:') and key[8:] in by and 'page-controls-2' not in line:
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
tot = len(detail)
app = sum(1 for r in detail if r['applied'] == 'applied')
res = sum(1 for r in detail if r['restored'] == 'restored')
pages_with = sorted({r['page'] for r in detail})
no_ctl = sorted(p for p in by if p not in pages_with)
led = ("A probe harness changed every parameter-bound numeric and check-box control by one step on %d more original Copter setup pages against a disposable SITL: %d changes, %d applied (read back from the vehicle), %d restored. "
       "Pages with such controls: %s. Pages with none found: %s. Combo boxes listed, not changed; the traditional-helicopter page was driven against a multirotor simulator; harness, not a person clicking."
       % (len(by), tot, app, res, ', '.join(pages_with), ', '.join(no_ctl)))
if 'ledger:setup-page-controls-more-copter' not in s:
    s += 'ledger:setup-page-controls-more-copter,3,,modified-copy,,partial,' + EVID + ',"' + led.replace('"', "'") + '"\n'
open(CLAIMS, 'wb').write(s.encode('utf-8'))
print('claims rows changed:', changed, '| changes', tot, 'applied', app, 'restored', res, '| no controls:', no_ctl)

raw = open(LEDGER, 'rb').read().decode('utf-8')
ls = raw.split('\n')
for i, l in enumerate(ls):
    if l.lstrip('\r').startswith('| Setup page controls: Copter failsafe and tuning pages |'):
        eol = '\r' if l.endswith('\r') else ''
        new = ('| Setup page controls: more Copter pages | Partial | `research-tools/PageControlsProbe.cs` changed every parameter-bound numeric and check-box control by one step on %d more original setup pages against a disposable Copter SITL '
               '(AC_Fence, compass, parachute, radio input and output, ESC calibration, and the traditional-helicopter page driven against a multirotor simulator): %d changes, %d applied and read back from the vehicle, %d restored. '
               'Pages with no such controls (%s) were not changed. Combo boxes listed, not changed; harness, not a person clicking. Evidence in `sitl-evidence/page-controls-2/`. |'
               % (len(by), tot, app, res, ', '.join(no_ctl))) + eol
        if 'Setup page controls: more Copter pages' not in raw:
            ls.insert(i + 1, new)
        break
open(LEDGER, 'wb').write('\n'.join(ls).encode('utf-8'))

t = open(TRACE, 'rb').read().decode('utf-8')
add = '''
## More Copter pages (second controls run)

The same probe was run over %d more pages (`sitl-evidence/page-controls-2/`): %d parameter changes (numeric steps and check-box toggles), %d applied (read back from the vehicle), %d restored. Pages with such controls: %s. Pages where no bound numeric or check-box control was found, so nothing was changed: %s (they use other write paths or only combo boxes). `ConfigRadioOutput` accounted for 64 of the changes (48 numeric, 16 check boxes). `ConfigTradHeli4` is the traditional-helicopter page and was driven against the multirotor simulator, so those writes only show the controls work.

One message box appeared: `ConfigAC_Fence` raised "Set FENCE_ENABLE Failed" even though the read-back shows both writes reached the vehicle; the check box's callback re-downloads the parameter list (`ConfigAC_Fence.cs` line 21) and I did not examine why the page reported a failure. Combo boxes were not changed in either run.

The first controls run's results are in `sitl-evidence/page-controls/` (kept separate on purpose; this run first overwrote them in the working tree and they were restored from the commit).
''' % (len(by), tot, app, res, ', '.join(pages_with), ', '.join(no_ctl))
if 'More Copter pages (second controls run)' not in t:
    t = t.rstrip('\n') + '\n' + add
open(TRACE, 'wb').write(t.encode('utf-8'))
print('ledger and trace ok')
