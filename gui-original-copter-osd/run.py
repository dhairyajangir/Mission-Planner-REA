"""Capture the two OSD navigation areas on an isolated disarmed Copter guest under Ubuntu-E."""
from pathlib import Path
import gzip
import hashlib
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BASE = REPO / "gui-original-mono-evidence-20261122"
WORK = Path("/tmp/mission-planner-original-gui-nov21")
ARCHIVE = REPO/"mission-planner-portable.zip"
SIM = Path("/home/think/ap-snapshot/build/sitl/bin/arducopter")

def launch(destination, udp=False, manual=False, empty=False):
    destination.mkdir(parents=True,exist_ok=False)
    root = WORK/"root"
    app = Path(tempfile.mkdtemp(prefix="app-osd-",dir=WORK))
    out = Path(tempfile.mkdtemp(prefix="osd-",dir=WORK/"results"))
    profile = Path(tempfile.mkdtemp(prefix="home-osd-",dir=WORK))
    print(out,flush=True)
    (out/"extracted-path.txt").write_text(str(app))
    if hashlib.sha256(SIM.read_bytes()).hexdigest() != "24afb2e186bcdf66c66d7cb5b88fb7afeaa2a0b89bf63c9d58e4fb2029ac2b54":
        raise ValueError("Unexpected simulator")
    subprocess.run(["unzip","-qo",ARCHIVE,"-d",app],check=True)
    startup = (REPO/"gui-original-copter-sensor-options/capture.sh").read_text().split("# An operator reads")[0]
    assert "mono --interp MissionPlanner.exe" in startup
    if udp or manual:
        startup = "\n".join(line for line in startup.splitlines() if "printf '<AutoConnect>" not in line) + "\n"
        startup = startup.replace("mono --interp MissionPlanner.exe", "mono MissionPlanner.exe")
    if udp:
        startup = startup.replace("./arducopter --model +", "./arducopter --model + --serial0=udpclient:127.0.0.1:14550")
    if manual:
        startup = startup.replace("printf '</Config>","printf '<comport>TCP</comport></Config>")
    if empty:
        startup = startup.replace("<comport>TCP", "<AutoConnect>[]</AutoConnect><comport>TCP")
    (out/"capture.sh").write_text(startup + ("MANUAL=1\n" if manual else "") + (HERE/"actions.sh").read_text())
    guest = [root/"usr/bin/bwrap","--die-with-parent","--new-session","--unshare-all","--cap-drop","ALL",
        "--clearenv","--ro-bind",root,"/","--proc","/proc","--dev","/dev","--tmpfs","/tmp",
        "--bind",profile,"/home/test","--tmpfs","/var/lib/xkb","--tmpfs","/sim","--ro-bind",SIM,"/sim/arducopter",
        "--bind",app,"/opt/mp","--bind",out,"/evidence","--chdir","/opt/mp","--setenv","HOME","/home/test",
        "--setenv","USER","test","--setenv","LANG","C.UTF-8","--setenv","PATH","/usr/bin:/bin",
        "--setenv","XDG_CONFIG_HOME","/home/test/.config","--setenv","XDG_DATA_HOME","/home/test/.local/share",
        "--setenv","DISPLAY",":44","--setenv","SKIP_STARTUP_PLUGINS","2","--setenv","USE_COPTER","1",
        "--setenv","LIBGL_ALWAYS_SOFTWARE","1","/bin/bash","/evidence/capture.sh"]
    proc = subprocess.run(guest)
    for src in sorted(out.glob("screen-*.xwd")):
        label = src.stem.removeprefix("screen-")
        if src.stat().st_size == 0:
            continue
        subprocess.run(["convert",src,destination/(label+".png")],check=True)
        shutil.copyfile(out/("windows-"+label+".txt"),destination/(label+"-tree.txt"))
    for name in ("observation.log","release.log","copter.log","initial-user-config.xml"):
        if (out/name).is_file(): shutil.copyfile(out/name,destination/name)
    for src in profile.rglob("*.tlog"):
        with src.open("rb") as f, gzip.open(destination/"vehicle.tlog.gz","wb") as g: shutil.copyfileobj(f,g)
    subprocess.run([sys.executable,BASE/"runtime/compare_archive.py",ARCHIVE,app,destination/"archive-comparison.json"],check=True)
    proc.check_returncode()

if __name__ == "__main__":
    launch(Path(sys.argv[1]), "--udp" in sys.argv[2:], "--manual" in sys.argv[2:], "--empty" in sys.argv[2:])
