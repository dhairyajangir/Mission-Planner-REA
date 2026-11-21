"""Compare the two GPS receive paths in the archived Mission Planner release."""
import argparse
import csv
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
ZIP = HERE.parent / "mission-planner-portable.zip"
ZIP_DIGEST = "ff3694f7a9038caf756545049dd7aef74e3d0d8fe3586e87aa881045704dd6f9"
ASSEMBLIES = ["MissionPlanner.ArduPilot.dll", "MissionPlanner.Utilities.dll", "MAVLink.dll"]
FIELDS = ["fix", "satellites", "hdop", "fix2", "satellites2", "hdop2", "combined_satellites"]
EXPECTED = {
    "valid": [3, 10, .85, 3, 10, .85, 20],
    "unknown": [1, 10, .85, 1, 255, 655.35, 265],
    "valid-zero": [1, 0, 0, 1, 0, 0, 0],
    "unknown-after-zero": [1, 0, 0, 1, 255, 655.35, 255],
    "recovery": [3, 8, .95, 3, 8, .95, 16],
}


def capture():
    with ZIP.open("rb") as file:
        digest = sha256()
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != ZIP_DIGEST:
        raise ValueError("Release archive differs")
    with tempfile.TemporaryDirectory() as folder, zipfile.ZipFile(ZIP) as archive:
        temp = Path(folder)
        for name in archive.namelist():
            if "/" not in name and name.lower().endswith((".dll", ".dll.config", "missionplanner.exe.config")):
                with archive.open(name) as original, (temp / name).open("wb") as local:
                    shutil.copyfileobj(original, local)
        shutil.copyfile(temp / "MissionPlanner.exe.config", temp / "probe.exe.config")
        compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
        subprocess.run([compiler, "/nologo", "/out:probe.exe", "/r:Microsoft.CSharp.dll",
                        "/r:" + str(compiler.with_name("netstandard.dll")), "/r:MAVLink.dll",
                        HERE / "GpsReceiverProbe.cs"], cwd=temp, check=True)
        run = subprocess.run([temp / "probe.exe"], cwd=temp, capture_output=True, text=True, check=True, timeout=60)
        rows = [row for row in csv.reader(run.stdout.splitlines()) if row and row[0] == "GPS"]
        if [row[1] for row in rows] != list(EXPECTED):
            raise ValueError(run.stdout)
        return {"archive_sha256": digest.hexdigest(), "assemblies": {
            n: sha256((temp / n).read_bytes()).hexdigest() for n in ASSEMBLIES},
            "stages": {row[1]: dict(zip(FIELDS, map(float, row[2:]), strict=True)) for row in rows}}


def verify(data=None):
    if data is None:
        data = json.loads((HERE / "observations.json").read_text())
    if data["stages"] != {stage: dict(zip(FIELDS, values, strict=True)) for stage, values in EXPECTED.items()}:
        raise ValueError(data["stages"])
    with zipfile.ZipFile(ZIP) as archive:
        if data["archive_sha256"] != ZIP_DIGEST or data["assemblies"] != {
            n: sha256(archive.read(n)).hexdigest() for n in ASSEMBLIES}:
            raise ValueError("Assembly identity differs")
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    if args.record or args.replay:
        result = verify(capture())
        if args.record:
            (HERE / "observations.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        elif result != verify():
            raise SystemExit("Fresh capture differs")
    print(verify()["stages"]["unknown"])
