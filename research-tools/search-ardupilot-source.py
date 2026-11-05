"""Search the verified-source snapshot using SQLite FTS5 query syntax."""
import sqlite3
import sys
from pathlib import Path

if len(sys.argv) == 2:
    project, query = 'ardupilot', sys.argv[1]
elif len(sys.argv) == 3 and sys.argv[1] == '--mission-planner':
    project, query = 'mission-planner-normalized', sys.argv[2]
elif len(sys.argv) == 3 and sys.argv[1] == '--submodules':
    project, query = 'ardupilot-submodules', sys.argv[2]
else:
    raise SystemExit('Usage: python research-tools/search-ardupilot-source.py [--mission-planner|--submodules] "FTS5 query"')
root = Path(__file__).resolve().parent.parent
filename = ('ardupilot-submodules-index.sqlite' if project == 'ardupilot-submodules' else project + '-source-index.sqlite')
db = root / 'integration-research' / filename
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro', uri=True) as connection:
    rows = connection.execute("SELECT path, snippet(source_text, 1, '[', ']', ' ... ', 20) "
                              'FROM source_text WHERE source_text MATCH ? LIMIT 30', (query,))
    for path, excerpt in rows:
        print(path + '\n  ' + ' '.join(excerpt.split()) + '\n')
