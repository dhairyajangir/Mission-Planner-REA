"""Regenerate the pinned release IL and execute the value comparison against MAVLink.dll."""
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import hashlib
import os
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CSC = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
ASSEMBLIES = ["MAVLink.dll", "MissionPlanner.ArduPilot.dll", "MissionPlanner.exe"]

def inspect():
    with TemporaryDirectory() as folder, ZipFile(REPO / "mission-planner-portable.zip") as release:
        tmp = Path(folder)
        cecil = shutil.copy(REPO / "research-tools/Mono.Cecil.dll", tmp)
        header = []
        for name in ASSEMBLIES:
            data = release.read(name)
            (tmp / name).write_bytes(data)
            header.append(name + " SHA256 " + hashlib.sha256(data).hexdigest())
        subprocess.run([str(CSC), "/nologo", "/reference:" + str(cecil), "/out:InspectBattery.exe",
                        str(HERE / "InspectBattery.cs")], cwd=tmp, check=True)
        output = subprocess.check_output([str(tmp / "InspectBattery.exe"), *ASSEMBLIES], cwd=tmp).decode()
        return "\n".join(header) + "\n" + output.replace("\r\n", "\n")

if __name__ == "__main__":
    (HERE / "release-il.txt").write_text(inspect(), encoding="utf-8")
