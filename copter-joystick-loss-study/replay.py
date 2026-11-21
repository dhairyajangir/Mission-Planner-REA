"""Replay the release joystick mapping and unplug fixture with no device or open link."""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RELEASE = ROOT / "mission-planner-portable"
ARCHIVE = ROOT / "mission-planner-portable.zip"
GOLDEN = ROOT / "coverage/golden/joystick-pickchannel.csv"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def capture():
    compiler = Path(os.environ["SystemRoot"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    references = ["MissionPlanner.exe", "MissionPlanner.ArduPilot.dll", "MissionPlanner.Comms.dll",
                  "MissionPlanner.Utilities.dll", "MAVLink.dll", "log4net.dll"]
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(ARCHIVE) as archive:
        work = Path(tmp)
        exe = work / "MappingProbe.exe"
        compile_args = [str(compiler), "/nologo", "/main:IsolatedProbe", "/out:" + str(exe)]
        compile_args.append("/r:" + str(compiler.parent / "netstandard.dll"))
        compile_args.extend("/r:" + str(RELEASE / name) for name in references)
        compile_args.extend([str(HERE / "IsolatedProbe.cs"), str(HERE / "ConfirmedLifecycle.cs"),
                             str(ROOT / "research-tools/JoystickMappingProbe.cs")])
        subprocess.run(compile_args, cwd=work, check=True, timeout=60)
        results = []
        for run in range(2):
            run_dir = work / str(run)
            run_dir.mkdir()
            output = run_dir / "values.csv"
            proc = subprocess.run([str(exe), str(RELEASE), str(output)], cwd=run_dir, capture_output=True,
                                  text=True, errors="replace", timeout=60)
            if proc.returncode:
                raise RuntimeError((proc.stdout + proc.stderr)[-4000:])
            lines = proc.stdout.splitlines()
            files = {}
            for line in lines:
                if line.startswith("RELEASE_FILE="):
                    name = line.split("=", 1)[1]
                    original = archive.read(name)
                    if (RELEASE / name).read_bytes() != original:
                        raise ValueError("Loaded assembly differs: " + name)
                    files[name] = sha(original)
            if not {"MAVLink.dll", "MissionPlanner.ArduPilot.dll", "MissionPlanner.Utilities.dll"} <= set(files):
                raise ValueError("Missing release assembly identity")
            rows = list(csv.reader(io.StringIO(output.read_text())))
            with GOLDEN.open(newline="") as source:
                if rows != list(csv.reader(source)):
                    raise ValueError("Mapping vectors differ from the archived capture")
            canonical = "\n".join(",".join(row) for row in rows) + "\n"
            results.append({"loaded_release_files": files, "mapped_rows": len(rows) - 1,
                            "mapping_sha256": sha(canonical.encode()),
                            "lifecycle": [line for line in lines if line.startswith("CONFIRMED_")]})
        if results[0] != results[1]:
            raise ValueError({k: (results[0][k], results[1][k]) for k in results[0] if results[0][k] != results[1][k]})
        return results[0]


def verify():
    result = json.loads((HERE / "observations.json").read_text())
    expected = ["CONFIRMED_STARTED ENABLED=True CH1=2000 CH3=1000",
                "CONFIRMED_INVALID ENABLED=True CH1=1000 CH3=1000",
                "CONFIRMED_CLEARED ENABLED=False CH1=0 CH3=0"]
    if result["lifecycle"] != expected or result["mapped_rows"] != 1092:
        raise ValueError("Lifecycle or mapping count changed")
    if result["mapping_sha256"] != sha(GOLDEN.read_text().encode()):
        raise ValueError("Archived mapping differs")
    with zipfile.ZipFile(ARCHIVE) as archive:
        for name, digest in result["loaded_release_files"].items():
            if sha(archive.read(name)) != digest:
                raise ValueError("Unexpected archived assembly: " + name)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    if args.record or args.replay:
        actual = capture()
        if args.record:
            (HERE / "observations.json").write_text(json.dumps(actual, sort_keys=True, indent=2) + "\n")
        elif actual != verify():
            raise SystemExit("Captured result differs")
    print(verify()["lifecycle"])
