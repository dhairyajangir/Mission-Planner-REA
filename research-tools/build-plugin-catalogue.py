"""Write coverage/plugin-catalogue.csv: one row per bundled Mission Planner plugin or example script under
mission-planner-1.3.83-source/Plugins, with what its source references (static scan; nothing is executed).

A plugin is a project folder (compiled DLL) or a loose .cs file the application compiles at start-up. Columns count textual
references only: a count above zero shows the source mentions the thing, not that it runs. `--check` fails if stale.
"""
import csv
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / 'mission-planner-1.3.83-source/Plugins'
OUT = ROOT / 'coverage/plugin-catalogue.csv'
FIELDS = ['plugin', 'kind', 'files', 'lines', 'plugin_class', 'host_calls', 'mavlink_calls', 'network', 'serial_or_udp', 'file_io',
          'ui', 'threads_timers', 'process_start']
PATTERNS = {
    'network': r'WebClient|HttpClient|HttpWebRequest|WebRequest|Download(?:String|File|Data)|https?://|TcpClient|Socket',
    'serial_or_udp': r'SerialPort|UdpClient|ICommsSerial|CommsSerialPort',
    'file_io': r'File\.(?:Read|Write|Open|Create|Exists|Copy|Delete)|Directory\.|StreamReader|StreamWriter|FileStream',
    'ui': r'new Form|UserControl|ToolStripMenuItem|\.Controls\.Add|MessageBox|CustomMessageBox|\bButton\b',
    'threads_timers': r'new Thread|Task\.Run|Timer\b|ThreadPool|BackgroundWorker',
    'process_start': r'Process\.Start',
}
MAV = ['doCommand', 'doCommandInt', 'setMode', 'doARM', 'setParam', 'GetParam', 'sendPacket', 'setWP', 'getWP', 'setPositionTargetGlobalInt',
       'setGuidedModeWP', 'requestDatastream', 'SubscribeToPacketType', 'OnPacketReceived']


def strip(text):
    text = re.sub(r'/\*.*?\*/', ' ', text, flags=re.S)
    return re.sub(r'//[^\n]*', ' ', text)


def row(name, kind, files):
    text = strip('\n'.join(f.read_text(encoding='utf-8-sig', errors='replace') for f in files))
    cls = sorted(set(re.findall(r'class\s+(\w+)\s*:\s*(?:MissionPlanner\.)?(?:Plugin\.)?Plugin\b', text)))
    host = sorted(set(re.findall(r'Host\.(\w+)', text)))
    mav = sorted(m for m in MAV if re.search(r'\b' + m + r'\b', text))
    r = {'plugin': name, 'kind': kind, 'files': len(files), 'lines': text.count('\n') + 1, 'plugin_class': ';'.join(cls),
         'host_calls': ';'.join(host[:12]), 'mavlink_calls': ';'.join(mav)}
    for k, rx in PATTERNS.items():
        r[k] = len(re.findall(rx, text))
    return r


def main():
    rows = []
    for d in sorted(p for p in PLUGINS.iterdir() if p.is_dir()):
        files = sorted(f for f in d.rglob('*.cs') if not f.name.endswith('.Designer.cs'))
        if files:
            rows.append(row(d.name, 'project', files))
    for f in sorted(PLUGINS.glob('*.cs')):
        if not f.name.endswith('.Designer.cs'):
            rows.append(row(f.stem, 'loose-script', [f]))
    buf = io.StringIO(newline='')
    w = csv.DictWriter(buf, FIELDS, lineterminator='\n')
    w.writeheader()
    w.writerows(rows)
    text = buf.getvalue()
    if '--check' in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding='utf-8') != text:
            print('STALE plugin-catalogue.csv')
            raise SystemExit(1)
        print(f'OK {len(rows)} plugins')
        return
    OUT.write_text(text, encoding='utf-8', newline='\n')
    print(f'wrote {len(rows)} plugins -> {OUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
