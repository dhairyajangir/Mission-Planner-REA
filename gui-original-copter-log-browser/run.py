"""Launch or inspect one disconnected, private release process in Ubuntu-E."""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BASE = REPO / "gui-original-mono-evidence-20261122"
WORK = Path("/tmp/mission-planner-original-gui-nov21")
SAMPLE = REPO / "sitl-evidence/nonempty-log-probe/downloaded.bin"
ARCHIVE = REPO.parent / "mission-planner-portable.zip"

def launch():
    out = Path(tempfile.mkdtemp(prefix="logbrowse-", dir=WORK / "results"))
    app = Path(tempfile.mkdtemp(prefix="app-logbrowse-", dir=WORK))
    print(out.name, flush=True)
    subprocess.run(["unzip", "-qo", ARCHIVE, "-d", app], check=True)
    (out / "extracted-path.txt").write_text(str(app))
    startup = (BASE / "disconnected/capture.sh").read_text().split("# An operator reads")[0]
    (out / "capture.sh").write_text(startup + (HERE / "actions.sh").read_text())
    root = WORK / "root"
    subprocess.run([root / "usr/bin/bwrap", "--die-with-parent", "--new-session", "--unshare-all",
        "--cap-drop", "ALL", "--clearenv", "--ro-bind", root, "/", "--proc", "/proc", "--dev", "/dev",
        "--tmpfs", "/tmp", "--tmpfs", "/home/test", "--tmpfs", "/var/lib/xkb",
        "--bind", app, "/opt/mp", "--bind", out, "/evidence",
        "--ro-bind", SAMPLE, "/evidence/downloaded.bin", "--chdir", "/opt/mp",
        "--setenv", "HOME", "/home/test", "--setenv", "USER", "test", "--setenv", "LANG", "C.UTF-8",
        "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "XDG_CONFIG_HOME", "/home/test/.config",
        "--setenv", "XDG_DATA_HOME", "/home/test/.local/share", "--setenv", "DISPLAY", ":29",
        "--setenv", "SKIP_STARTUP_PLUGINS", "2", "--setenv", "LIBGL_ALWAYS_SOFTWARE", "1",
        "/bin/bash", "/evidence/capture.sh"], check=True)
    subprocess.run([sys.executable, BASE / "runtime/compare_archive.py", ARCHIVE, app, out / "archive-comparison.json"], check=True)

def observe(run, step, label, action, x, y):
    if not re.fullmatch(r"logbrowse-[a-zA-Z0-9_]{8}", run) or not re.fullmatch(r"[a-z0-9-]+", label):
        raise ValueError("Invalid run or label")
    out = WORK / "results" / run
    if step:
        with (out / f"action-{step}").open("x") as handle:
            print(action, x, y, label, file=handle)
    if action == "done":
        return
    raw = out / f"screen-{label}.xwd"
    for _ in range(300):
        if raw.exists() and raw.stat().st_size >= 1280 * 800 * 4:
            break
        time.sleep(0.5)
    else:
        raise RuntimeError("Guest screenshot did not arrive")
    subprocess.run(["convert", raw, HERE / "preview.png"], check=True)

if __name__ == "__main__":
    if sys.argv[1:] == ["launch"]:
        launch()
    else:
        p = argparse.ArgumentParser()
        p.add_argument("run")
        p.add_argument("step", type=int)
        p.add_argument("label")
        p.add_argument("action", choices=["click", "repeat", "double", "filename", "enter", "down", "up", "right", "home", "gps", "wheel", "space", "done", "observe"])
        p.add_argument("x", type=int, default=0, nargs="?")
        p.add_argument("y", type=int, default=0, nargs="?")
        observe(**vars(p.parse_args()))
