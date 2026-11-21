"""Offline replay of eight Copter GPS quality/position transitions using Mission Planner 1.3.83."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from zipfile import ZipFile

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New capture directory")
    output = parser.parse_args().output.resolve()
    source = Path(__file__).with_name("CopterGpsFixHudProbe.cs")
    with tempfile.TemporaryDirectory() as scratch:
        temp = Path(scratch)
        capture = temp / "evidence"
        capture.mkdir()
        with ZipFile(ROOT / "mission-planner-portable.zip") as archive:
            for name in archive.namelist():
                if "/" not in name and name.lower().endswith((".dll", ".dll.config", "missionplanner.exe.config")):
                    with archive.open(name) as original, (temp / name).open("wb") as target:
                        shutil.copyfileobj(original, target)
        shutil.copyfile(temp / "MissionPlanner.exe.config", temp / "probe.exe.config")
        compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
        subprocess.run([compiler, "/nologo", "/out:probe.exe", "/r:Microsoft.CSharp.dll", "/r:System.Drawing.dll",
                        "/r:" + str(compiler.with_name("netstandard.dll")), "/r:MAVLink.dll", source],
                       cwd=temp, check=True)
        subprocess.run([temp / "probe.exe", capture], cwd=temp, check=True, timeout=65)
        expected = [
            ("raw-3d", 3, 12, .85, 10, 20, 101, 0), ("raw-lost-last-position", 1, 4, 2.75, 10, 20, 101, 0),
            ("raw-lost-zero-position", 1, 4, 2.75, 0, 0, 0, 0), ("raw-recovered", 3, 11, .95, 10.01, 20.01, 102, 0),
            ("global-position", 3, 11, .95, 10.1, 20.1, 123, 12), ("global-lost", 1, 3, 3.15, 10.1, 20.1, 123, 12),
            ("global-update-while-lost", 1, 3, 3.15, 10.11, 20.11, 124, 13),
            ("global-recovered", 3, 11, .95, 10.11, 20.11, 124, 13)]
        with (capture / "observed.csv").open(newline="") as stream:
            rows = list(csv.reader(stream))[1:]
        actual = [(name, *map(float, values)) for name, *values in rows]
        if actual != expected:
            raise ValueError(f"Unexpected receive state: {actual}")
        def difference(a, b):
            with Image.open(capture / (a + ".png")) as first, Image.open(capture / (b + ".png")) as second:
                return ImageChops.difference(first.convert("RGB"), second.convert("RGB")).getbbox()
        loss = difference("raw-3d", "raw-lost-last-position")
        restored = difference("raw-3d", "raw-recovered")
        if loss is None or restored is not None:
            raise ValueError(f"Unexpected HUD comparison: lost={loss}, recovered={restored}")
        files = [source, temp / "MissionPlanner.Controls.dll", temp / "MissionPlanner.ArduPilot.dll",
                 temp / "MissionPlanner.Utilities.dll", temp / "MAVLink.dll", *sorted(capture.iterdir())]
        result = {"stages_verified": len(actual), "hud_loss_difference_bounds": loss,
                  "hud_recovered_equals_initial": True,
                  "sha256": {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
        (capture / "verification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        shutil.copytree(capture, output)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
