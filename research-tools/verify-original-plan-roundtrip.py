"""Verify the saved release-GUI file roundtrip and its retained provenance."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "gui-original-plan-evidence"


def read_wpl(path):
    lines = path.read_text(encoding="ascii").splitlines()
    if lines[0] != "QGC WPL 110":
        raise ValueError(f"Incorrect WPL header in {path.name}")
    rows = [tuple(map(Decimal, line.split("\t"))) for line in lines[1:]]
    if len(rows) != 3 or any(len(row) != 12 for row in rows):
        raise ValueError(f"Expected three 12-field rows in {path.name}")
    return rows


def main():
    second = ROOT / "roundtrip"
    src, dst = second / "input.waypoints", second / "saved.waypoints"
    if src.read_bytes() != (ROOT / "input.waypoints").read_bytes():
        raise ValueError("The two guests used different inputs")
    rows = read_wpl(src)
    if rows != read_wpl(dst) or src.read_bytes() == dst.read_bytes():
        raise ValueError("Expected equal numeric values with different formatting")
    observed = [tuple(r[k] for k in (0, 1, 2, 3, 8, 9, 10, 11)) for r in rows]
    expected = [
        "0 1 0 16 -35.363260 149.165230 584 1",
        "1 0 3 16 -35.362700 149.165900 23 1",
        "2 0 3 16 -35.362100 149.166400 37 1",
    ]
    if observed != [tuple(map(Decimal, record.split())) for record in expected]:
        raise ValueError("Unexpected waypoint fixture")
    for directory in (ROOT, second):
        report = json.loads((directory / "archive-comparison.json").read_text())
        if (report["release_files"], report["matching"], report["missing"], report["changed"]) != (1317, 1317, [], []):
            raise ValueError("Unexpected release comparison")
        if report["archive_sha256"] != "ff3694f7a9038caf756545049dd7aef74e3d0d8fe3586e87aa881045704dd6f9":
            raise ValueError("Unexpected release ZIP hash")
    for path, label in [(ROOT / "accepted-home-tree.txt", "Loaded plan-readback.waypoints"),
                        (second / "save-result-tree.txt", "Saved plan-saved.waypoints")]:
        if label not in path.read_text(encoding="utf-8"):
            raise ValueError(f"Missing application state: {label}")
    print("PASS: two release extractions, two GUI status labels, three WPL rows, 36 equal numeric fields.")
    for f in (src, dst):
        print(f.name, hashlib.sha256(f.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
