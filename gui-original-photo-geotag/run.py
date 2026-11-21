"""Capture the GeoRef form using the ordinary tools menu in the prepared Ubuntu-E guest."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BASE = REPO / "gui-original-mono-evidence-20261122"
WORK = Path("/tmp/mission-planner-original-gui-nov21")
ARCHIVE = REPO / "mission-planner-portable.zip"

def run(destination):
    destination.mkdir(parents=True,exist_ok=False)
    app = Path(tempfile.mkdtemp(prefix="app-photo-",dir=WORK))
    out = Path(tempfile.mkdtemp(prefix="photo-",dir=WORK / "results"))
    print(out, flush=True)
    root = WORK / "root"
    subprocess.run(["unzip","-qo",ARCHIVE,"-d",app],check=True)
    start = (BASE/"disconnected/capture.sh").read_text().split("# An operator reads")[0]
    (out/"capture.sh").write_text(start + (HERE/"actions.sh").read_text())
    guest = [root/"usr/bin/bwrap","--die-with-parent","--new-session","--unshare-all","--cap-drop","ALL",
        "--clearenv","--ro-bind",root,"/","--proc","/proc","--dev","/dev","--tmpfs","/tmp",
        "--tmpfs","/home/test","--tmpfs","/var/lib/xkb","--bind",app,"/opt/mp","--bind",out,"/evidence",
        "--chdir","/opt/mp","--setenv","HOME","/home/test","--setenv","USER","test","--setenv","LANG","C.UTF-8",
        "--setenv","PATH","/usr/bin:/bin","--setenv","XDG_CONFIG_HOME","/home/test/.config",
        "--setenv","XDG_DATA_HOME","/home/test/.local/share","--setenv","DISPLAY",":43",
        "--setenv","SKIP_STARTUP_PLUGINS","2","--setenv","LIBGL_ALWAYS_SOFTWARE","1","/bin/bash","/evidence/capture.sh"]
    proc = subprocess.run(guest)
    for file in sorted(out.glob("screen-*.xwd")):
        label = file.stem.removeprefix("screen-")
        subprocess.run(["convert",file,destination/(label+".png")],check=True)
        shutil.copyfile(out/("windows-"+label+".txt"),destination/(label+"-tree.txt"))
    for name in ("release.log","observation.log","initial-user-config.xml"):
        if (out/name).is_file(): shutil.copyfile(out/name,destination/name)
    subprocess.run([sys.executable,BASE/"runtime/compare_archive.py",ARCHIVE,app,destination/"archive-comparison.json"],check=True)
    proc.check_returncode()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination",type=Path,help="fresh directory for this observation")
    run(parser.parse_args().destination)
