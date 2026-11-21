"""Rerun the legacy sphere fit twice against the locally archived Windows release."""
import argparse
import hashlib
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
PIN = "ff3694f7a9038caf756545049dd7aef74e3d0d8fe3586e87aa881045704dd6f9"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def observe(exe, work, archive):
    proc = subprocess.run([str(exe), str(RELEASE)], cwd=work, capture_output=True,
                          text=True, check=True, timeout=60)
    fits, assemblies, method = {}, {}, None
    for line in proc.stdout.splitlines():
        fields = line.split("|")
        if fields[0] == "FIT":
            case, count, *coordinates = fields[1:]
            fits[case] = {"count": int(count), "offset_xyz_radius": list(map(float, coordinates))}
        elif fields[0] == "RELEASE":
            name = fields[1]
            original = archive.read(name)
            if (RELEASE / name).read_bytes() != original:
                raise ValueError("Loaded file differs from portable ZIP: " + name)
            assemblies[name] = sha(original)
        elif fields[0] == "METHOD":
            method = {"token": fields[1], "module_version_id": fields[2]}
    if set(fits) != {"full_sphere", "level_ring", "ring_plus_poles"} or not method:
        raise ValueError("Incomplete original-method output: " + proc.stdout[-600:])
    if not {"MissionPlanner.exe", "alglibnet.dll"} <= set(assemblies):
        raise ValueError("Missing loaded fit libraries")
    return {"archive_sha256": PIN, "method": method, "loaded_release_files": assemblies, "fits": fits}


def replay():
    compiler = Path(os.environ["SystemRoot"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    if sha(ARCHIVE.read_bytes()) != PIN:
        raise ValueError("Unexpected release archive")
    with zipfile.ZipFile(ARCHIVE) as archive, tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        exe = work / "OrientationProbe.exe"
        subprocess.run([str(compiler), "/nologo", "/out:" + str(exe), str(HERE / "OrientationProbe.cs")],
                       cwd=work, check=True, timeout=60)
        first = observe(exe, work, archive)
        second = observe(exe, work, archive)
        if first != second:
            raise ValueError("Independent fit processes disagreed")
        return first


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    actual = replay()
    saved = HERE / "fit-results.json"
    if args.check:
        if json.loads(saved.read_text()) != actual:
            raise SystemExit("Original fit differs from the retained result")
    else:
        saved.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n", encoding="utf8")
    print(json.dumps(actual["fits"]))
