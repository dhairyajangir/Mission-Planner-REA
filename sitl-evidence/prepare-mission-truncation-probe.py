"""Create a shorter rejected replacement-mission test without overwriting evidence."""
from pathlib import Path

base = Path(__file__).resolve().parent
source = (base / 'mission-partial-write.py').read_text()
replacements = {
    'archive-mission-partial-write': 'archive-mission-rejected-truncation',
    'port = 6520': 'port = 6530',
    "'-I', '76'": "'-I', '77'",
    '(-353629000, 1491656000, 30.0)]': '(-353629000, 1491656000, 30.0), (-353628000, 1491657000, 40.0)]',
    'link.mav.mission_count_send(link.target_system, link.target_component, len(baseline))':
        'link.mav.mission_count_send(link.target_system, link.target_component, len(baseline) - 1 if invalid_frame else len(baseline))',
    "before.get('count') == 3": "before.get('count') == 4",
}
for old, new in replacements.items():
    if old not in source:
        raise ValueError('expected source fragment not found: ' + old)
    source = source.replace(old, new)
target = base / 'mission-rejected-truncation.py'
if target.exists():
    raise FileExistsError(target)
target.write_text(source)
