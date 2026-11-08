"""Append the third PageControlsProbe run (numeric, check-box and combo-box controls, sitl-evidence/page-controls-3/) to the matching mp-page rows
in coverage/claims.csv, add a ledger row, the matching row in Reverse-Engineering-Coverage.md and a section in Setup-Page-Actions-Trace.md.
Run once; rows that already mention the evidence folder are skipped.
"""
import csv
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, 'sitl-evidence', 'page-controls-3')
CLAIMS = os.path.join(ROOT, 'coverage', 'claims.csv')
LEDGER = os.path.join(ROOT, 'Reverse-Engineering-Coverage.md')
TRACE = os.path.join(ROOT, 'Setup-Page-Actions-Trace.md')
EVID = ('sitl-evidence/page-controls-3/page-controls.csv;sitl-evidence/page-controls-3/page-controls-summary.csv;sitl-evidence/page-controls-3/message-boxes.txt;'
        'sitl-evidence/page-controls-3/console.txt;research-tools/PageControlsProbe.cs;research-tools/run-page-controls-probe.ps1;Setup-Page-Actions-Trace.md')

summ = list(csv.DictReader(open(os.path.join(D, 'page-controls-summary.csv'), newline='')))
detail = list(csv.DictReader(open(os.path.join(D, 'page-controls.csv'), newline='')))
by = {s['page']: s for s in summ}


def note(s):
    return ("Third controls run (probe harness, not a person, Copter SITL; adds combo boxes): numeric %s changed / %s applied / %s restored; check boxes %s / %s / %s; combo boxes %s changed of %s found / %s applied / %s restored "
            "(each moved one item, value compared with the control's own write rule and read back with GetParam, then put back)."
            % (s['numeric_changed'], s['numeric_applied'], s['numeric_restored'], s['checkbox_changed'], s['checkbox_applied'], s['checkbox_restored'],
               s['combo_changed'], s['combo_listed'], s['combo_applied'], s['combo_restored']))


lines = open(CLAIMS, 'rb').read().decode('utf-8').split('\n')
out, changed = [], 0
for line in lines:
    key = line.split(',', 1)[0]
    if key.startswith('mp-page:') and key[8:] in by and 'page-controls-3' not in line:
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
kinds = {k: [r for r in detail if r['kind'] == k] for k in ('numeric', 'checkbox', 'combo')}
tot, app, res = len(detail), sum(r['applied'] == 'applied' for r in detail), sum(r['restored'] == 'restored' for r in detail)
led = ("Third controls run: a probe harness changed %d parameter-bound controls by one step on %d original Copter setup pages against a disposable SITL (%d numeric, %d check box, %d combo box): %d applied (read back from the vehicle), %d restored. "
       "Combo boxes were compared with the control's own write rule (selected key or parsed enum). The tuning page's combo boxes (staged write) were not changed. Harness, not a person clicking; the trad-heli page was driven against a multirotor simulator."
       % (tot, len(by), len(kinds['numeric']), len(kinds['checkbox']), len(kinds['combo']), app, res))
if 'ledger:setup-page-controls-with-combos' not in s:
    s += 'ledger:setup-page-controls-with-combos,3,,modified-copy,,partial,' + EVID + ',"' + led.replace('"', "'") + '"\n'
open(CLAIMS, 'wb').write(s.encode('utf-8'))
print('claims rows changed:', changed, '| total', tot, 'applied', app, 'restored', res, {k: len(v) for k, v in kinds.items()})

raw = open(LEDGER, 'rb').read().decode('utf-8')
ls = raw.split('\n')
for i, l in enumerate(ls):
    if l.lstrip('\r').startswith('| Setup page controls: more Copter pages |'):
        eol = '\r' if l.endswith('\r') else ''
        new = ('| Setup page controls: combo boxes | Partial | A third `PageControlsProbe` run changed %d parameter-bound controls by one step on %d original Copter setup pages (%d numeric, %d check box, %d combo box) against a disposable SITL: %d applied and read back from the vehicle, %d restored. '
               'Combo boxes were compared with the control\'s own write rule (selected key or parsed enum value); the tuning page\'s combo boxes (staged write) were not changed. Harness, not a person clicking. Evidence in `sitl-evidence/page-controls-3/`. |'
               % (tot, len(by), len(kinds['numeric']), len(kinds['checkbox']), len(kinds['combo']), app, res)) + eol
        if 'Setup page controls: combo boxes' not in raw:
            ls.insert(i + 1, new)
        break
open(LEDGER, 'wb').write('\n'.join(ls).encode('utf-8'))

t = open(TRACE, 'rb').read().decode('utf-8')
add = '''
## Combo boxes (third controls run)

`PageControlsProbe` was extended to move each `MavlinkComboBox` to its next item on pages without a staged write button, compare the vehicle's value with what the control writes (the selected key for key/value sources, or the enum value parsed from the text for enum sources) and put it back. Run on %d pages (`sitl-evidence/page-controls-3/`): %d controls changed (%d numeric, %d check box, %d combo box), %d applied, %d restored. Examples: `BATT_MONITOR` moved from "Analog Voltage and Current" (4) to "Bebop" (6), `FENCE_ACTION` from "RTL or Land" (1) to "Always Land" (2), `COMPASS_ORIENT` from "None" (0) to "Yaw45" (1); each read back as expected and was restored.

A first run of this version labelled the combo "target" text after the control had been put back, so it named the original item; the compared values were right but the label was wrong. I fixed the probe, discarded that output and reran; only the corrected run is in the repository. The combo boxes on the tuning page (staged write) and on pages not in this list were not changed. As before, `ConfigAC_Fence` raised "Set FENCE_ENABLE Failed" with a correct read-back, cause not examined.
''' % (len(by), tot, len(kinds['numeric']), len(kinds['checkbox']), len(kinds['combo']), app, res)
if 'Combo boxes (third controls run)' not in t:
    t = t.rstrip('\n') + '\n' + add
open(TRACE, 'wb').write(t.encode('utf-8'))
print('ledger and trace ok')
