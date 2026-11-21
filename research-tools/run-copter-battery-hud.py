"""Capture the release HUD's lower-left battery display using its software renderer."""
import argparse
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
    parser.add_argument("output", type=Path, help="New evidence directory")
    output = parser.parse_args().output.resolve()
    source = Path(__file__).with_name("CopterBatteryHudProbe.cs").resolve()
    compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    with tempfile.TemporaryDirectory(prefix="mp-hud-battery-") as temp:
        work = Path(temp)
        captures = work / "captures"
        captures.mkdir()
        with ZipFile(ROOT / "mission-planner-portable.zip") as archive:
            for name in archive.namelist():
                if "/" not in name and name.lower().endswith((".dll", ".dll.config", "missionplanner.exe.config")):
                    with archive.open(name) as src, (work / name).open("wb") as dest:
                        shutil.copyfileobj(src, dest)
        shutil.copyfile(work / "MissionPlanner.exe.config", work / "probe.exe.config")
        subprocess.run([compiler, "/nologo", "/out:probe.exe", "/r:Microsoft.CSharp.dll",
                        "/r:System.Drawing.dll", source], cwd=work, check=True)
        subprocess.run([work / "probe.exe", captures], cwd=work, check=True, timeout=90)
        checks = []
        for left, right, equal in [
            ("dual-valid", "primary-empty", False),
            ("primary-unknown", "primary-empty", True),
            ("secondary-unknown", "secondary-empty", False),
            ("secondary-no-volts-unknown", "secondary-no-volts-empty", True),
            ("icons-secondary-unknown", "icons-secondary-empty", True),
            ("icons-secondary-unknown", "dual-valid", False),
        ]:
            with Image.open(captures / (left + ".png")) as a, Image.open(captures / (right + ".png")) as b:
                bounds = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox()
            if (bounds is None) != equal:
                raise ValueError(f"Unexpected crop difference: {left} vs {right}, {bounds}")
            checks.append({"left": left, "right": right, "difference_bounds": bounds})
        files = [source, work / "MissionPlanner.Controls.dll", work / "MissionPlanner.ArduPilot.dll"]
        hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files + sorted(captures.glob("*.png"))}
        (captures / "results.json").write_text(json.dumps({"comparisons": checks, "sha256": hashes},
                                                         indent=2) + "\n", encoding="utf-8")
        shutil.copytree(captures, output)
    print("PASS: nine HUD crops; six RGB comparisons.")


if __name__ == "__main__":
    main()
