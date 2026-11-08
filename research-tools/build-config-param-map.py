"""Write coverage/config-page-params.csv and config-page-params-summary.md: which parameter names each Mission Planner
setup page (GCSViews/ConfigurationView/*.cs) mentions, how, and whether the pinned ArduPilot snapshot declares them.

Static text scan only. It finds quoted upper-case names in these call shapes:
  setup-alias  <control>.setup(... new[] {"NAME", "OLD_NAME", ...} ...)   (alternative names across firmware versions)
  read         MAV.param["NAME"], param.ContainsKey("NAME"), param[new[] {"A","B"}]
  write        <port>.setParam(... "NAME" ...)  (also the array overloads)
  get          <port>.GetParam(... "NAME" ...)
It does NOT see names built at run time (for example "RC" + n + "_MIN"), names set through control properties in the
designer, or pages outside ConfigurationView. Reading a name proves a page mentions it, not that the page works.

    python research-tools/build-config-param-map.py          # rewrite the two files
    python research-tools/build-config-param-map.py --check  # fail if they are stale
"""
import csv
import io
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / 'mission-planner-1.3.83-source/GCSViews/ConfigurationView'
NAMES = ROOT / 'coverage/ardupilot-param-names.csv'
OUT = ROOT / 'coverage/config-page-params.csv'
SUMMARY = ROOT / 'coverage/config-page-params-summary.md'
NAME_RE = re.compile(r'"([A-Z][A-Z0-9_]*[A-Z0-9])"')
FIELDS = ['page', 'control', 'kind', 'name', 'line', 'declared_in_snapshot']
PARTIAL = 'partial'  # literal is joined to another string with '+', so only part of the name is known


def strip_comments(text):
    """Blank out // and /* */ comments but keep line numbers."""
    text = re.sub(r'/\*.*?\*/', lambda m: re.sub(r'[^\n]', ' ', m.group(0)), text, flags=re.S)
    return re.sub(r'//[^\n]*', lambda m: ' ' * len(m.group(0)), text)


def call_span(text, start):
    """Return the text of the balanced parentheses beginning at text[start] == '('."""
    depth, i, in_str = 0, start, False
    while i < len(text):
        c = text[i]
        if in_str:
            if c == '\\':
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    return text[start:]


def scan(path):
    text = strip_comments(path.read_text(encoding='utf-8-sig', errors='replace'))
    line_of = lambda pos: text.count('\n', 0, pos) + 1
    found = []

    def add(kind, control, span, pos):
        for m in NAME_RE.finditer(span):
            before, after = span[:m.start()].rstrip(), span[m.end():].lstrip()
            joined = before.endswith('+') or after.startswith('+')
            found.append((kind, control, m.group(1), line_of(pos), joined))

    for m in re.finditer(r'(\w+)\.setup\s*\(', text):
        add('setup-alias', m.group(1), call_span(text, m.end() - 1), m.start())
    for m in re.finditer(r'\bsetParam\s*\(', text):
        add('write', '', call_span(text, m.end() - 1), m.start())
    for m in re.finditer(r'\bGetParam\s*\(', text):
        add('get', '', call_span(text, m.end() - 1), m.start())
    for m in re.finditer(r'\bparam\s*\[\s*(?:new\s*(?:string)?\s*\[\s*\]\s*)?(\{[^}]*\}|"[^"]*")', text):
        add('read', '', m.group(1), m.start())
    for m in re.finditer(r'\bContainsKey\s*\(\s*("[^"]*")', text):
        add('read', '', m.group(1), m.start())
    return found


def load_known():
    with NAMES.open(encoding='utf-8', newline='') as f:
        return {r['name'] for r in csv.DictReader(f)}


def build():
    known = load_known()
    rows = []
    for path in sorted(PAGES.glob('*.cs')):
        if path.name.endswith('.Designer.cs'):
            continue
        seen = set()
        for kind, control, name, line, joined in scan(path):
            key = (kind, control, name, line)
            if key in seen:
                continue
            seen.add(key)
            rows.append({'page': path.stem, 'control': control, 'kind': kind, 'name': name, 'line': line,
                         'declared_in_snapshot': PARTIAL if joined else ('yes' if name in known else 'no')})
    rows.sort(key=lambda r: (r['page'], r['line'], r['kind'], r['control'], r['name']))
    return rows, known


def summary(rows):
    pages = defaultdict(list)
    for r in rows:
        pages[r['page']].append(r)
    names = {r['name'] for r in rows}
    unknown = sorted({r['name'] for r in rows if r['declared_in_snapshot'] == 'no'})
    partial = sorted({r['name'] for r in rows if r['declared_in_snapshot'] == PARTIAL})
    # alias lists: all rows of one setup(...) call share page, control and line range; group by (page, control, line)
    calls = defaultdict(list)
    for r in rows:
        if r['kind'] == 'setup-alias':
            calls[(r['page'], r['control'], r['line'])].append(r)
    dead = sorted(k for k, v in calls.items() if all(x['declared_in_snapshot'] == 'no' for x in v))
    n_alias = len(calls)
    lines = ['# Setup-page parameter map', '',
             'Generated by `research-tools/build-config-param-map.py`. Do not edit.', '',
             f'{len(pages)} pages in `GCSViews/ConfigurationView` mention at least one parameter name; {len(names)} distinct names; '
             f'{len(unknown)} of them are not declared by the pinned ArduPilot snapshot (see `coverage/ardupilot-param-names.csv`); '
             f'{len(partial)} more appear only joined to another string (for example a prefix) and cannot be checked.',
             '', 'A name missing from the snapshot is usually an old alias kept for older firmware. A `setup` call whose '
             f'names are **all** missing is listed below as a control that cannot find its parameter in this snapshot ({len(dead)} of {n_alias} alias lists). '
             'Joined names are excluded from that count.', '',
             '| Page | Names | Not declared | Reads | Writes | Gets | Alias lists |', '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for page in sorted(pages):
        v = pages[page]
        lines.append(f"| {page} | {len({r['name'] for r in v})} | {len({r['name'] for r in v if r['declared_in_snapshot'] == 'no'})} | "
                     f"{sum(r['kind'] == 'read' for r in v)} | {sum(r['kind'] == 'write' for r in v)} | "
                     f"{sum(r['kind'] == 'get' for r in v)} | {len({(r['control'], r['line']) for r in v if r['kind'] == 'setup-alias'})} |")
    lines += ['', f'## Alias lists with no name in the snapshot ({len(dead)})', '']
    lines += [f'- `{p}` control `{c}` (line {ln}): ' + ', '.join(f"`{x['name']}`" for x in calls[(p, c, ln)]) for p, c, ln in dead] or ['None.']
    lines += ['', '## Names not declared by the snapshot', '', ', '.join(f'`{n}`' for n in unknown), '',
              '## Names seen only as part of a joined string', '', ', '.join(f'`{n}`' for n in partial), '']
    return '\n'.join(lines)


def render(rows):
    buf = io.StringIO(newline='')
    w = csv.DictWriter(buf, FIELDS, lineterminator='\n')
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def main():
    rows, _ = build()
    text, summ = render(rows), summary(rows)
    if '--check' in sys.argv:
        stale = [p.name for p, t in ((OUT, text), (SUMMARY, summ)) if not p.exists() or p.read_text(encoding='utf-8') != t]
        if stale:
            print('STALE ' + ', '.join(stale))
            raise SystemExit(1)
        print(f'OK {len(rows)} rows')
        return
    OUT.write_text(text, encoding='utf-8', newline='\n')
    SUMMARY.write_text(summ, encoding='utf-8', newline='\n')
    print(f'wrote {len(rows)} rows, {len({r["page"] for r in rows})} pages')


if __name__ == '__main__':
    main()
