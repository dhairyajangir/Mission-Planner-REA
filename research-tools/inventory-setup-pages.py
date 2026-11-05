"""Index explicit configuration page registrations; runtime conditions are not evaluated."""
import csv
from pathlib import Path
import re

root = Path(__file__).resolve().parent.parent
source = root / 'mission-planner-1.3.83-source/GCSViews'
out = root / 'mission-planner-binary-evidence/configuration-page-source-inventory.csv'
pattern = re.compile(r'AddBackstageViewPage\s*\(\s*typeof\s*\(\s*([\w.]+)\s*\)')
rows = []
for name in ('InitialSetup.cs', 'SoftwareConfig.cs'):
    path = source / name
    for line_number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        if line.lstrip().startswith('//'):
            continue
        match = pattern.search(line)
        if match:
            rows.append((name, line_number, match.group(1), line.strip()))
with out.open('w', encoding='utf-8', newline='') as stream:
    writer = csv.writer(stream)
    writer.writerow(('source_file', 'line', 'page_type', 'registration_first_line'))
    writer.writerows(rows)
print(f'{len(rows)} explicit page registrations indexed in {out}')
