"""Replay the offline Auto Analysis UI using the archived text conversion, under Ubuntu-E."""
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BASE = REPO / "gui-original-mono-evidence-20261122"
WORK = Path("/tmp/mission-planner-original-gui-nov21")
ARCHIVE = REPO.parent / "mission-planner-portable.zip"
SAMPLE = REPO / "sitl-evidence/nonempty-log-probe/converted.log"
DIGEST = "2a09825386071ec0a636c61edbf6296d10e189fe440835ef253c21063b1d7576"

def run():
    if hashlib.sha256(SAMPLE.read_bytes()).hexdigest() != DIGEST:
        raise ValueError("Unexpected archived text log")
    root = WORK / "root"
    out = Path(tempfile.mkdtemp(prefix="analyzer-", dir=WORK / "results"))
    app = Path(tempfile.mkdtemp(prefix="app-analyzer-", dir=WORK))
    print(out.name, flush=True)
    subprocess.run(["unzip", "-qo", ARCHIVE, "-d", app], check=True)
    startup = (BASE / "disconnected/capture.sh").read_text().split("# An operator reads")[0]
    (out / "capture.sh").write_text(startup + (HERE / "actions.sh").read_text())
    result = subprocess.run([root / "usr/bin/bwrap", "--die-with-parent", "--new-session",
        "--unshare-all", "--cap-drop", "ALL", "--clearenv", "--ro-bind", root, "/", "--proc", "/proc",
        "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/home/test", "--tmpfs", "/var/lib/xkb",
        "--bind", app, "/opt/mp", "--bind", out, "/evidence", "--ro-bind", SAMPLE, "/evidence/copter.log",
        "--chdir", "/opt/mp", "--setenv", "HOME", "/home/test", "--setenv", "USER", "test",
        "--setenv", "LANG", "C.UTF-8", "--setenv", "PATH", "/usr/bin:/bin",
        "--setenv", "XDG_CONFIG_HOME", "/home/test/.config", "--setenv", "XDG_DATA_HOME", "/home/test/.local/share",
        "--setenv", "DISPLAY", ":29", "--setenv", "SKIP_STARTUP_PLUGINS", "2",
        "--setenv", "LIBGL_ALWAYS_SOFTWARE", "1", "/bin/bash", "/evidence/capture.sh"])
    subprocess.run([sys.executable, BASE / "runtime/compare_archive.py", ARCHIVE, app, HERE / "archive-comparison.json"], check=True)
    for name in ("observation.log", "initial-user-config.xml"):
        shutil.copyfile(out / name, HERE / name)
    labels = ("analysis-menu", "file-picker", "download-result", "final-result", "unrecognized")
    for name in labels:
        frame = out / f"screen-{name}.xwd"
        if frame.exists():
            subprocess.run(["convert", frame, HERE / (name + ".png")], check=True)
            lines = (out / f"windows-{name}.txt").read_text().splitlines()
            selected = [s.strip() for s in lines if re.search(
                r'"(Auto Analysis|DataFlash Logs|Open|File name:|.*LogAnalyzer.*|Bad input file|OK|Log Files|.*/evidence/copter.log.*|.*[Aa]naly[sz].*)"', s)]
            (HERE / (name + ".txt")).write_text("\n".join(selected)+"\n")
    log = (out / "release.log").read_text(errors="replace").splitlines()
    (HERE / "release-excerpt.log").write_text("\n".join(s for s in log if
        any(t in s.lower() for t in ("appload time", "loganalyzer", "bad input file", "/evidence/copter.log"))) + "\n")
    result.check_returncode()

if __name__ == "__main__":
    run()
