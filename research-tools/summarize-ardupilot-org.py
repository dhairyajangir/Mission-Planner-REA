"""Create a readable index from a dated GitHub organization metadata capture."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
capture = root / 'mission-planner-binary-evidence/ardupilot-org-repos-2026-11-05.json'
pages = json.loads(capture.read_text(encoding='utf-8-sig'))
repos = [r for page in pages for r in page]
assert len({r['id'] for r in repos}) == len(repos)
assert all(r['owner']['login'].lower() == 'ardupilot' and not r['private'] for r in repos)
lines = ['# ArduPilot GitHub organization inventory', '',
         'Snapshot: 5 November 2026, from the GitHub public organization repositories API. '
         'Descriptions and repository status are GitHub metadata; this is an inventory, not a code review. '
         'The set can change. Forks and archived projects are included.', '',
         'Capture: `mission-planner-binary-evidence/ardupilot-org-repos-2026-11-05.json`',
         'Capture SHA-256: `' + hashlib.sha256(capture.read_bytes()).hexdigest() + '`',
         f"Public repositories in capture: {len(repos)}; archived: {sum(r['archived'] for r in repos)}; forks: {sum(r['fork'] for r in repos)}.", '',
         '| Repository | Description | Language | Flags |', '| --- | --- | --- | --- |']
for r in sorted(repos, key=lambda x: x['name'].casefold()):
    desc = (r['description'] or '').replace('|', '\\|').replace('\r', ' ').replace('\n', ' ')
    flags = ', '.join(x for x, yes in [('fork', r['fork']), ('archived', r['archived'])] if yes)
    lines.append(f"| [{r['name']}]({r['html_url']}) | {desc} | {r['language'] or ''} | {flags} |")
lines += ['', 'The supplied source archive is the `ardupilot` firmware repository snapshot; '
          'Mission Planner has a separate repository. Other entries have not been reverse engineered merely by appearing here.']
target = root / 'ArduPilot-Organization-Inventory.md'
target.write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(f'{len(repos)} repositories indexed in {target}')
