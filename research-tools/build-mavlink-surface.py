"""Write coverage/mavlink-surface.csv: which Mission Planner types call each MAVLinkInterface action method.

Source: the `calls` and `methods` tables in mission-planner-binary-evidence/rea-main-index.sqlite (MissionPlanner.exe IL).
Limits: direct call sites in the main executable only; no other assemblies, reflection, delegates or runtime dispatch.
Nested/compiler-generated types are folded into their outer type.
"""
import csv
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / 'mission-planner-binary-evidence/rea-main-index.sqlite'
OUT = ROOT / 'coverage/mavlink-surface.csv'
TARGET_TYPE = 'MissionPlanner.MAVLinkInterface'


def main():
    db = sqlite3.connect('file:' + DB.as_posix() + '?mode=ro', uri=True)
    sites = defaultdict(list)  # api method -> [(caller outer type, caller method)]
    query = """SELECT c.target_name, m.declaring_type, m.name FROM calls c
               JOIN methods m ON m.token = c.caller_token WHERE c.target_declaring_type = ?"""
    for api, caller_type, caller_method in db.execute(query, (TARGET_TYPE,)):
        if api == '.ctor' or api.startswith(('get_', 'set_')):
            continue
        sites[api].append(((caller_type or '?').split('/')[0], caller_method))
    rows = []
    for api, items in sites.items():
        types = Counter(t for t, _ in items)
        top = ';'.join(f'{t}({n})' for t, n in sorted(types.items(), key=lambda kv: (-kv[1], kv[0]))[:8])
        rows.append([api, len(items), len({m for _, m in items}), len(types), top])
    rows.sort(key=lambda r: (-r[1], r[0]))
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['api_method', 'call_sites', 'distinct_caller_methods', 'distinct_caller_types', 'top_caller_types'])
        w.writerows(rows)
    print(f'{len(rows)} MAVLinkInterface action methods, {sum(r[1] for r in rows)} call sites -> {OUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
