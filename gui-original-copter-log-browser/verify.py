"""Verify the retained original GUI session and compare its input with the component trace."""
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import struct

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent / "sitl-evidence"
SAMPLE = "80f2d22edb979b0e9fc219da3c2dbc3a0ff4b86a7d8611728276bc5732041d6d"
ZIP = "ff3694f7a9038caf756545049dd7aef74e3d0d8fe3586e87aa881045704dd6f9"
PNG = {
    "clean-time-graph": "e9d8f8fd039796d889fe720ae6cbdb95301391e9a6febf744550817097bfd617",
    "dataflash-logs": "fa83c51e30949e5d5e6b88288947e666c08bbc15d6c632c0140455b1d8a82e3e",
    "file-name": "25a2df48143149b6f11fb401e0ee25074a309c42cb968f1412141894a0789b8b",
    "gps-alt-time": "f525aa15b4eb86515eb09fa9be447d85c566d97361ff3e3dfeee88995e67f89d",
    "parsed": "17d5789c0707d7a83d6716ea700f054563ca7baf601e320331ad4813db605e4c",
}

def require(ok, message):
    if not ok:
        raise ValueError(message)

def verify():
    for name, digest in PNG.items():
        data = (HERE / (name + ".png")).read_bytes()
        require(hashlib.sha256(data).hexdigest() == digest, name)
        require(struct.unpack(">II", data[16:24]) == (1280, 800), name)
    comparison = json.loads((HERE / "archive-comparison.json").read_text())
    require(comparison["archive_sha256"] == ZIP, "Archive mismatch")
    require(comparison["matching"] == comparison["release_files"] == 1317 and
            not comparison["missing"] and not comparison["changed"], "Original release files")
    require(hashlib.sha256((EVIDENCE / "nonempty-log-probe/downloaded.bin").read_bytes()).hexdigest() == SAMPLE,
            "Retained log input")
    observation = (HERE / "observation.log").read_text()
    require(re.findall(r"^\s*(\w+):\s+\d+", observation, re.M) == ["lo"], "Guest interfaces")
    require(SAMPLE + "  /evidence/downloaded.bin" in observation, "Guest log input")
    actions = re.findall(r"^\S+Z \d+ \S+ \d+ \d+ ([\w-]+)$", observation, re.M)
    require(actions[3:] == ["dataflash-logs", "choose-log", "file-name", "open-log", "parsed",
            "gps-instance", "gps-fields", "gps-alt-time", "hide-errors", "hide-events",
            "clean-time-graph", "finish"], "Observed GUI operations")
    log = (HERE / "release-excerpt.log").read_text()
    require(all(s in log for s in ("appload time", "/evidence/downloaded.bin", "GraphItem: GPS Alt 0",
            "Graphing GPS - Alt", "GraphItem_GetList GPS Alt 0")), "Graph trace")
    require("Log Browser - downloaded.bin" in (HERE / "window-titles.log").read_text(), "Window title")
    component = EVIDENCE / "copter-log-gps-graph"
    meta = json.loads((component / "verification.json").read_text())
    require(meta["input_sha256"] == SAMPLE, "Component sample")
    raw = (component / "points.csv").read_bytes()
    require(hashlib.sha256(raw).hexdigest() == meta["points_sha256"], "Component points")
    with (component / "points.csv").open(newline="") as stream:
        rows = [row for row in csv.DictReader(stream) if row["axis"] == "x_time"]
    heights = [Decimal(row["y"]) for row in rows]
    require(heights == [Decimal("578.12")] + [Decimal("584.09")] * 390, "GPS altitude sequence")
    times = [Decimal(row["x"]) for row in rows]
    require(all(a < b for a, b in zip(times, times[1:])), "GPS time ordering")
    return {"release_files_matching": 1317, "screenshots": len(PNG), "gps_samples": len(rows),
            "all_sample_min_m": str(min(heights)), "all_sample_mean_m": str(round(sum(heights) / len(heights), 2)),
            "all_sample_max_m": str(max(heights)), "observed_legend_min_m": "584.09"}

if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
