"""Replay the battery percentage transitions using a temporary copy of the release assemblies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New evidence directory")
    output = parser.parse_args().output.resolve()
    source = Path(__file__).with_name("CopterBatteryRemainingProbe.cs").resolve()
    compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    with tempfile.TemporaryDirectory(prefix="mp-battery-remaining-") as temp:
        work = Path(temp)
        with ZipFile(ROOT / "mission-planner-portable.zip") as archive:
            for name in archive.namelist():
                if "/" not in name and name.lower().endswith((".dll", ".dll.config", "missionplanner.exe.config")):
                    with archive.open(name) as member, (work / name).open("wb") as target:
                        shutil.copyfileobj(member, target)
        shutil.copyfile(work / "MissionPlanner.exe.config", work / "probe.exe.config")
        subprocess.run([compiler, "/nologo", "/out:probe.exe", "/r:Microsoft.CSharp.dll",
                        "/r:" + str(compiler.with_name("netstandard.dll")), "/r:MAVLink.dll", source],
                       check=True, cwd=work)
        subprocess.run([work / "probe.exe", work / "states.csv"], cwd=work, check=True, timeout=45)
        states = (work / "states.csv").read_bytes()
        hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in
                  [work / "MissionPlanner.ArduPilot.dll", work / "MAVLink.dll",
                   work / "MissionPlanner.Utilities.dll", source, work / "states.csv"]}
    output.mkdir(parents=True, exist_ok=False)
    (output / "states.csv").write_bytes(states)
    (output / "sha256.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    print(states.decode("utf-8"), end="")


if __name__ == "__main__":
    main()
