"""Run both warning persistence phases with the portable DLL and a temporary profile."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from zipfile import ZipFile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new evidence directory")
    output = parser.parse_args().output
    root = Path(__file__).resolve().parents[1]
    libraries = root / "mission-planner-portable"
    dll = libraries / "MissionPlanner.Utilities.dll"
    source = Path(__file__).with_name("WarningsPersistenceProbe.cs").resolve()
    compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    with ZipFile(root / "mission-planner-portable.zip") as archive:
        released_bytes = archive.read(dll.name)
    if dll.read_bytes() != released_bytes:
        raise ValueError("Local utility DLL differs from the portable ZIP member")
    with tempfile.TemporaryDirectory(prefix="mp-warning-") as temp:
        profile = Path(temp) / "profile"
        executable = Path(temp) / "probe.exe"
        subprocess.run([str(compiler), "/nologo", "/reference:" + str(dll),
                        "/reference:" + str(compiler.with_name("netstandard.dll")),
                        "/out:" + str(executable), str(source)], check=True)
        logs = {}
        for phase in ("save", "load"):
            logs[phase] = subprocess.check_output(
                [str(executable), str(libraries), str(profile), phase],
                cwd=temp, text=True, timeout=30)
        xml = (profile / "Mission Planner/warnings.xml").read_bytes()
    output.mkdir(parents=True, exist_ok=False)
    (output / "warnings.xml").write_bytes(xml)
    for name, log in logs.items():
        (output / (name + ".txt")).write_text(log, encoding="utf-8")
    hashes = {dll.name: hashlib.sha256(released_bytes).hexdigest(),
              source.name: hashlib.sha256(source.read_bytes()).hexdigest(),
              "warnings.xml": hashlib.sha256(xml).hexdigest()}
    (output / "sha256.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    print(logs["save"] + logs["load"], end="")


if __name__ == "__main__":
    main()
