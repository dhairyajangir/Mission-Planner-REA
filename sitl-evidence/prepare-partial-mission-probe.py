"""Create a distinct partial-upload test from the invalid-frame probe."""
from pathlib import Path

base = Path(__file__).resolve().parent
source = (base / 'mission-invalid-frame.py').read_text()
replacements = {
    "archive-mission-invalid-frame": "archive-mission-partial-write",
    'port = 6510': 'port = 6520',
    "'-I', '75'": "'-I', '76'",
    "baseline = [(-353632610, 1491652300, 0.0), (-353630000, 1491655000, 20.0)]":
        "baseline = [(-353632610, 1491652300, 0.0), (-353630000, 1491655000, 20.0), (-353629000, 1491656000, 30.0)]",
    'invalid_frame and msg.seq == 1 else': 'invalid_frame and msg.seq == 2 else',
    '        frame = 255 if invalid_frame': '        if invalid_frame and msg.seq == 1:\n            altitude = 25.0\n        frame = 255 if invalid_frame',
    "before.get('count') == 2": "before.get('count') == 3",
}
for old, new in replacements.items():
    if old not in source:
        raise ValueError('expected source fragment not found: ' + old)
    source = source.replace(old, new)
target = base / 'mission-partial-write.py'
if target.exists():
    raise FileExistsError(target)
target.write_text(source)
