"""Capture original SETUP > Optional Hardware > Joystick inside the existing offline Mono runtime."""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "gui-original-mono-evidence-20261122"
ARCHIVE = HERE.parent.parent / "mission-planner-portable.zip"
WORK = Path("/tmp/mission-planner-original-gui-nov21")

def run():
    root = WORK / "root"
    out = Path(tempfile.mkdtemp(prefix="joystick-", dir=WORK / "results"))
    app = Path(tempfile.mkdtemp(prefix="app-joystick-", dir=WORK))
    print(out.name, flush=True)
    subprocess.run(["unzip", "-qo", ARCHIVE, "-d", app], check=True)
    startup = (BASE / "disconnected/capture.sh").read_text().split("# An operator reads")[0]
    (out / "capture.sh").write_text(startup + (HERE / "actions.sh").read_text())
    result = subprocess.run([root / "usr/bin/bwrap", "--die-with-parent", "--new-session",
        "--unshare-all", "--cap-drop", "ALL", "--clearenv", "--ro-bind", root, "/", "--proc", "/proc",
        "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/home/test", "--tmpfs", "/var/lib/xkb",
        "--bind", app, "/opt/mp", "--bind", out, "/evidence", "--chdir", "/opt/mp",
        "--setenv", "HOME", "/home/test", "--setenv", "USER", "test", "--setenv", "LANG", "C.UTF-8",
        "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "XDG_CONFIG_HOME", "/home/test/.config",
        "--setenv", "XDG_DATA_HOME", "/home/test/.local/share", "--setenv", "DISPLAY", ":57",
        "--setenv", "SKIP_STARTUP_PLUGINS", "2", "--setenv", "LIBGL_ALWAYS_SOFTWARE", "1",
        "/bin/bash", "/evidence/capture.sh"])
    subprocess.run([sys.executable, BASE / "runtime/compare_archive.py", ARCHIVE, app, HERE / "archive-comparison.json"], check=True)
    for name in ("observation.log", "initial-user-config.xml"):
        shutil.copyfile(out / name, HERE / name)
    for name in ("setup", "optional", "joystick", "settled"):
        frame = out / f"screen-{name}.xwd"
        if frame.exists():
            subprocess.run(["convert", frame, HERE / (name + ".png")], check=True)
            tree = (out / f"windows-{name}.txt").read_text().splitlines()
            (HERE / (name + ".txt")).write_text("\n".join(s.strip() for s in tree if re.search(
                r'"(?:.*Joystick.*|.*Hardware.*|RC \d+|Reverse|Expo|Output|Controller Axis|Manual Control|Elevons|Enable|Save|Loaded Config for.*|Detect.*|Error|OK|[+-])"', s, re.I)) + "\n")
    lines = (out / "release.log").read_text(errors="replace").splitlines()
    (HERE / "release-excerpt.log").write_text("\n".join(s for s in lines if any(t in s.lower()
        for t in ("appload time", "joystick", "open missionplanner.gcsviews.initialsetup", "configoptional"))) + "\n")
    result.check_returncode()

if __name__ == "__main__":
    run()
