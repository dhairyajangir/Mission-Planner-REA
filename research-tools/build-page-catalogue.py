"""Write coverage/page-catalogue.csv: one row per Mission Planner screen source (setup pages plus the main GCSViews),
listing what its code does at the source level: MAVLink calls, MAV_CMD names, parameter names, outside I/O.

Static text scan of the .cs file next to each page type (and its non-designer partials). It records what the code
mentions, not what runs: conditional branches, dead code and run-time-built values are all counted. `--check` fails when
the committed file is stale.
"""
import csv
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MP = ROOT / 'mission-planner-1.3.83-source'
INV = ROOT / 'mission-planner-binary-evidence/configuration-page-source-inventory.csv'
PARAMS = ROOT / 'coverage/config-page-params.csv'
OUT = ROOT / 'coverage/page-catalogue.csv'
FIELDS = ['page', 'source', 'lines', 'mavlink_calls', 'mav_cmds', 'param_names', 'param_writes', 'firmware_branches',
          'network', 'file_io', 'dialogs', 'threads_timers', 'plugins_or_external_tools']
CALLS = ['doCommand', 'doCommandInt', 'setMode', 'doARM', 'setParam', 'GetParam', 'getParamList', 'setWP', 'getWP', 'getWPCount',
         'setWPTotal', 'setGuidedModeWP', 'setPositionTargetGlobalInt', 'requestDatastream', 'sendPacket', 'setMountControl',
         'SetSensorOffsets', 'getRallyPoint', 'setRallyPoint', 'getFencePoint', 'setFencePoint', 'getRequestedWPNo', 'Open', 'Close']
PATTERNS = {
    'network': r'WebClient|HttpClient|HttpWebRequest|WebRequest|Download(?:String|File|Data)|https?://|TcpClient|UdpClient',
    'file_io': r'File\.(?:Read|Write|Open|Create|Exists|Copy|Delete)|Directory\.|StreamReader|StreamWriter|OpenFileDialog|SaveFileDialog',
    'dialogs': r'CustomMessageBox\.Show|MessageBox\.Show',
    'threads_timers': r'new Thread|ThreadPool|Task\.Run|System\.Timers\.Timer|Windows\.Forms\.Timer|\bTimer\s+\w+\s*=|BackgroundWorker|ProgressReporterDialogue',
    'plugins_or_external_tools': r'Process\.Start|Plugin|\.exe"',
}


def strip_comments(text):
    text = re.sub(r'/\*.*?\*/', ' ', text, flags=re.S)
    return re.sub(r'//[^\n]*', ' ', text)


_INDEX = {}


def locate(page):
    """Path of the .cs file that declares the page class (last dotted segment), preferring GCSViews and Joystick/Antenna dirs."""
    if not _INDEX:
        for p in MP.rglob('*.cs'):
            if 'ExtLibs' in p.parts or p.name.endswith('.Designer.cs'):
                continue
            _INDEX.setdefault(p.stem.lower(), []).append(p)
    cands = _INDEX.get(page.split('.')[-1].lower(), [])
    return sorted(cands, key=lambda p: ('ConfigurationView' not in p.parts, len(p.parts)))[0] if cands else None


def sources_for(page, source_file):
    base = locate(page)
    if base is None:
        return []
    paths = [base] + [p for p in sorted(base.parent.glob(base.stem + '.*.cs')) if not p.name.endswith('.Designer.cs')]
    return paths


def count(rx, text):
    return len(re.findall(rx, text))


def main():
    pages = {}
    with INV.open(encoding='utf-8', newline='') as f:
        for r in csv.DictReader(f):
            pages.setdefault(r['page_type'], r['source_file'])
    for name in ('FlightData', 'FlightPlanner', 'InitialSetup', 'SoftwareConfig', 'Help', 'SITL'):
        pages.setdefault(name, 'GCSViews/' + name + '.cs')
    params = {}
    with PARAMS.open(encoding='utf-8', newline='') as f:
        for r in csv.DictReader(f):
            d = params.setdefault(r['page'].lower(), {'names': set(), 'writes': set()})
            d['names'].add(r['name'])
            if r['kind'] == 'write':
                d['writes'].add(r['name'])
    rows = []
    for page in sorted(pages):
        files = sources_for(page, pages[page])
        src = files[0].relative_to(MP).as_posix() if files else ''
        if not files:
            rows.append({'page': page, 'source': src, 'lines': 0, **{k: '' for k in FIELDS[3:]}})
            continue
        text = strip_comments('\n'.join(p.read_text(encoding='utf-8-sig', errors='replace') for p in files))
        calls = sorted({c for c in CALLS if re.search(r'\.' + c + r'\s*\(', text)})
        cmds = sorted(set(re.findall(r'MAV_CMD\.([A-Z0-9_]+)', text)))
        fw = sorted(set(re.findall(r'Firmwares\.(\w+)', text)))
        row = {'page': page, 'source': src, 'lines': text.count('\n') + 1, 'mavlink_calls': ';'.join(calls),
               'mav_cmds': ';'.join(cmds), 'param_names': len(params.get(page.split('.')[-1].lower(), {}).get('names', ())),
               'param_writes': len(params.get(page.split('.')[-1].lower(), {}).get('writes', ())), 'firmware_branches': ';'.join(fw)}
        for k, rx in PATTERNS.items():
            row[k] = count(rx, text)
        rows.append(row)
    buf = io.StringIO(newline='')
    w = csv.DictWriter(buf, FIELDS, lineterminator='\n')
    w.writeheader()
    w.writerows(rows)
    text = buf.getvalue()
    if '--check' in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding='utf-8') != text:
            print('STALE page-catalogue.csv')
            raise SystemExit(1)
        print(f'OK {len(rows)} pages')
        return
    OUT.write_text(text, encoding='utf-8', newline='\n')
    print(f'wrote {len(rows)} pages -> {OUT.relative_to(ROOT)}')
    print('no source found:', [r['page'] for r in rows if not r['lines']])


if __name__ == '__main__':
    main()
