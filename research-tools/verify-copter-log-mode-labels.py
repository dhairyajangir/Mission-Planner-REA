"""Replay the release DataFlash callback and compare both conversions with retained bytes."""
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "mission-planner-portable"
EVIDENCE = ROOT / "sitl-evidence/copter-log-mode-labels"
FIRMWARE = ROOT / "ardupilot-source/ardupilot-master/ArduCopter/mode.h"
RELEASE_FILES = ("MissionPlanner.exe", "MissionPlanner.Utilities.dll", "MissionPlanner.ArduPilot.dll",
                 "MissionPlanner.exe.config", "ParameterMetaDataBackup.xml")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_modes(path):
    with path.open(encoding="ascii") as log:
        return [(int(t), label, int(num), int(reason))
                for tag, t, label, num, reason in (
                    row for row in csv.reader(log, skipinitialspace=True) if row[0] == "MODE")]


def main():
    hashes = {}
    with zipfile.ZipFile(ROOT / "mission-planner-portable.zip") as archive:
        for name in RELEASE_FILES:
            data = (RELEASE / name).read_bytes()
            if data != archive.read(name):
                raise ValueError(f"Local release file differs from ZIP: {name}")
            hashes[name] = digest(data)
    firmware_enum = FIRMWARE.read_text(encoding="utf-8").split("enum class Number : uint8_t {")[1].split("};")[0]
    modes = {int(num): name for name, num in re.findall(r"^\s*(\w+)\s*=\s*(\d+)\s*,", firmware_enum, re.M)}
    raw = ET.parse(RELEASE / "ParameterMetaDataBackup.xml").findtext("./ArduCopter2/FLTMODE1/Values")
    labels = dict(item.split(":", 1) for item in raw.split(","))
    compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    with tempfile.TemporaryDirectory() as tmp:
        temp = Path(tmp)
        runner = temp / "CopterLogModeProbe.exe"
        subprocess.run([compiler, "/nologo", "/r:System.Xml.Linq.dll", "/out:" + str(runner),
                        ROOT / "research-tools/CopterLogModeProbe.cs"], check=True)
        shutil.copyfile(RELEASE / "MissionPlanner.exe.config", str(runner) + ".config")
        run = subprocess.run([runner, RELEASE, temp], capture_output=True, text=True, check=True, timeout=45)
        if "callback=MissionPlanner.MainV2+<>c.<OnLoad>b__142_3" not in run.stdout:
            raise ValueError("Unexpected desktop callback")
        capture = {}
        for file in ("mode-series.bin", "with-handler.log", "without-handler.log"):
            data = (temp / file).read_bytes()
            if data != (EVIDENCE / file).read_bytes():
                raise ValueError(f"Retained fixture or output differs: {file}")
            capture[file] = digest(data)
        nums = list(range(31))
        expected = [(1, "5", 5, 0)] + [(3+n, labels.get(str(n), str(n)), n, 0) for n in nums]
        if read_modes(temp / "with-handler.log") != expected:
            raise ValueError("Application callback output differs from bundled metadata")
        if read_modes(temp / "without-handler.log") != [(t, str(n), n, r) for t, _, n, r in expected]:
            raise ValueError("Standalone output differs from numeric control")
    if set(modes) - set(nums):
        raise ValueError("Fixture does not span pinned Copter enum")
    print(json.dumps({"firmware_enum_sha256": digest(FIRMWARE.read_bytes()), "release_sha256": hashes,
                      "capture_sha256": capture, "firmware_modes": len(modes),
                      "named_pinned_modes": sum(str(num) in labels for num in modes),
                      "pinned_modes_without_bundled_label": {num: name for num, name in modes.items()
                                                            if str(num) not in labels},
                      "checked_mode_records_per_run": len(expected)}, indent=2))


if __name__ == "__main__":
    main()
