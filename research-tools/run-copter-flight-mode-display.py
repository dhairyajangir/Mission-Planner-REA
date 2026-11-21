"""Run the unshown ConfigFlightModes page with synthetic Copter state on Windows."""
import hashlib
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
EXE_HASH = "a49e30e2cd635836cd737f112f419da2d3c46c59716ee08122e2986013b79f2a"


def main(output):
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    with tempfile.TemporaryDirectory(prefix="mp-flight-mode-display-") as temp:
        work = Path(temp)
        with ZipFile(ROOT / "mission-planner-portable.zip") as archive:
            for name in archive.namelist():
                if "/" not in name and name.lower().endswith((".dll", ".dll.config", "missionplanner.exe", "missionplanner.exe.config")):
                    with archive.open(name) as member, (work / name).open("wb") as target:
                        shutil.copyfileobj(member, target)
        if hashlib.sha256((work / "MissionPlanner.exe").read_bytes()).hexdigest() != EXE_HASH:
            raise ValueError("Release executable does not match the recorded 1.3.83 SHA-256")
        shutil.copyfile(work / "MissionPlanner.exe.config", work / "Probe.exe.config")
        subprocess.run([compiler, "/nologo", "/out:Probe.exe", "/r:System.Windows.Forms.dll",
                        "/r:System.Drawing.dll", "/r:Microsoft.CSharp.dll",
                        ROOT / "research-tools/CopterFlightModeDisplayProbe.cs"], cwd=work, check=True)
        subprocess.run([work / "Probe.exe", output], cwd=work, check=True, timeout=90)


if __name__ == "__main__":
    main(sys.argv[1])
