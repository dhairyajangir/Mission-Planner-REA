"""Read the original release's page-registration instructions without loading its UI."""
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import os
import shutil
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

def inspect():
    csc = Path(os.environ["WINDIR"])/"Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    with TemporaryDirectory() as folder, zipfile.ZipFile(REPO/"mission-planner-portable.zip") as release:
        d = Path(folder)
        exe = release.read("MissionPlanner.exe")
        sha = hashlib.sha256(exe).hexdigest()
        if sha != "a49e30e2cd635836cd737f112f419da2d3c46c59716ee08122e2986013b79f2a":
            raise ValueError("Release mismatch")
        (d/"MissionPlanner.exe").write_bytes(exe)
        shutil.copy(REPO/"research-tools/Mono.Cecil.dll",d)
        subprocess.run([str(csc),"/nologo","/r:Mono.Cecil.dll","/out:Registration.exe",str(HERE/"Registration.cs")],cwd=d,check=True)
        out = subprocess.check_output([str(d/"Registration.exe"),"MissionPlanner.exe"],cwd=d,text=True)
    return "SHA256 " + sha + "\n" + out

if __name__ == "__main__":
    (HERE/"registration.txt").write_text(inspect(),encoding="utf-8")
