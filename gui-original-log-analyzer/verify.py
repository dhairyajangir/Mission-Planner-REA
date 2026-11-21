"""Verify the recorded original-GUI Auto Analysis attempt without starting Mission Planner."""
import hashlib
import json
from pathlib import Path
import re
import struct

HERE = Path(__file__).resolve().parent
ZIP = "ff3694f7a9038caf756545049dd7aef74e3d0d8fe3586e87aa881045704dd6f9"
INPUT = "2a09825386071ec0a636c61edbf6296d10e189fe440835ef253c21063b1d7576"
SHOTS = {
    "analysis-menu": "fa83c51e30949e5d5e6b88288947e666c08bbc15d6c632c0140455b1d8a82e3e",
    "file-picker": "9f9ad80884dbab81ec155d6cce66bbd8664d5168b6c4dc56328b23430e51fe10",
    "download-result": "449c052eae94f9c2661cff2ecd5d7f1cf17d7ada4f9598050c8abc673d98c15d",
    "final-result": "9b18b09b1850f4dd5085c34832b96d9bceddeb9da09e1a81f1365bd0f2aa869a",
}

def require(ok, subject):
    if not ok:
        raise ValueError(subject)

def verify():
    for label, digest in SHOTS.items():
        data = (HERE / (label + ".png")).read_bytes()
        require(hashlib.sha256(data).hexdigest() == digest, label)
        require(struct.unpack(">II", data[16:24]) == (1280, 800), label)
    comparison = json.loads((HERE / "archive-comparison.json").read_text())
    require(comparison["archive_sha256"] == ZIP and comparison["matching"] == comparison["release_files"] == 1317
            and not comparison["changed"] and not comparison["missing"], "Original release files")
    members = json.loads((HERE / "release-members.json").read_text())
    require(members == {"zip_sha256": ZIP, "release_file_count": 1317, "runner_exe_members": [],
                        "loganalyzer_members": []}, "Release runner inventory")
    sample = HERE.parent / "sitl-evidence/nonempty-log-probe/converted.log"
    raw = sample.read_bytes()
    require(len(raw) == 8267692 and hashlib.sha256(raw).hexdigest() == INPUT, "Archived text log")
    observation = (HERE / "observation.log").read_text()
    require(re.findall(r"^\s*(\w+):\s+\d+", observation, re.M) == ["lo"], "Guest interfaces")
    require(INPUT + "  /evidence/copter.log" in observation and
            "Submitted /evidence/copter.log using the Open button." in observation, "Guest input")
    for label, strings in (("analysis-menu", ("DataFlash Logs", "Auto Analysis")),
                           ("file-picker", ("Open", "File name:")),
                           ("download-result", ("Failed to download LogAnalyzer", "OK")),
                           ("final-result", ("Bad input file", "OK"))):
        tree = (HERE / (label + ".txt")).read_text()
        require(all(f'"{value}"' in tree for value in strings), label + " window tree")
    trace = (HERE / "release-excerpt.log").read_text()
    require("Downloading LogAnalyzer" in trace and "/LogAnalyzer/LogAnalyzer64.zip" in trace, "Runner request")
    return {"original_release_files": 1317, "local_input_bytes": len(raw), "file_picker": True,
            "download_error": "Failed to download LogAnalyzer", "follow_up": "Bad input file",
            "analysis_report_observed": False}

if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
