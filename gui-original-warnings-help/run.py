"""Capture Help and Warnings in a disconnected Mission Planner release; run under Ubuntu-E."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BASE = REPO / "gui-original-mono-evidence-20261122"
WORK = Path("/tmp/mission-planner-original-gui-nov21")
ARCHIVE = REPO.parent / "mission-planner-portable.zip"

def launch(replay=False):
    root = WORK / "root"
    out = Path(tempfile.mkdtemp(prefix="warnhelp-", dir=WORK / "results"))
    app = Path(tempfile.mkdtemp(prefix="app-warnhelp-", dir=WORK))
    print(out.name, flush=True)
    (out / "extracted-path.txt").write_text(str(app))
    subprocess.run(["unzip", "-qo", ARCHIVE, "-d", app], check=True)
    startup = (BASE / "disconnected/capture.sh").read_text().split("# An operator reads")[0]
    (out / "capture.sh").write_text(startup + (HERE / "actions.sh").read_text())
    steps = [
        ("help-page", "click", 390, 117), ("tools-opening", "ctrlf", 0, 0),
        ("tools-ready", "waittools", 0, 0), ("manager-open", "showmanager", 0, 0),
        ("manager-repaint", "redrawmanager", 0, 0), ("finish", "done", 0, 0),
    ]
    if replay:
        for i, (label, action, x, y) in enumerate(steps, 1):
            (out / f"action-{i}").write_text(f"{action} {x} {y} {label}\n")
    subprocess.run([root / "usr/bin/bwrap", "--die-with-parent", "--new-session", "--unshare-all",
        "--cap-drop", "ALL", "--clearenv", "--ro-bind", root, "/", "--proc", "/proc", "--dev", "/dev",
        "--tmpfs", "/tmp", "--tmpfs", "/home/test", "--tmpfs", "/var/lib/xkb", "--bind", app, "/opt/mp",
        "--bind", out, "/evidence", "--chdir", "/opt/mp", "--setenv", "HOME", "/home/test",
        "--setenv", "USER", "test", "--setenv", "LANG", "C.UTF-8", "--setenv", "PATH", "/usr/bin:/bin",
        "--setenv", "XDG_CONFIG_HOME", "/home/test/.config", "--setenv", "XDG_DATA_HOME", "/home/test/.local/share",
        "--setenv", "DISPLAY", ":29", "--setenv", "SKIP_STARTUP_PLUGINS", "2",
        "--setenv", "LIBGL_ALWAYS_SOFTWARE", "1", "/bin/bash", "/evidence/capture.sh"], check=True)
    subprocess.run([sys.executable, BASE / "runtime/compare_archive.py", ARCHIVE, app, HERE / "archive-comparison.json"], check=True)
    for name in ["observation.log", "initial-user-config.xml"]:
        shutil.copyfile(out / name, HERE / name)
    if replay:
        for label in ("help-page", "tools-ready", "manager-open", "manager-repaint"):
            step(out.name, 0, label, "observe", 0, 0)
        subprocess.run([sys.executable, "-B", HERE / "retain.py", out.name, "--manager", "manager-repaint"], check=True)

def step(run, index, label, action, x, y):
    if not re.fullmatch(r"warnhelp-[a-z0-9_]{8}", run) or not re.fullmatch(r"[a-z0-9-]+", label):
        raise ValueError("Invalid session or label")
    out = WORK / "results" / run
    if index:
        with (out / f"action-{index}").open("x") as f:
            print(action, x, y, label, file=f)
    if action == "done":
        return
    image = out / f"screen-{label}.xwd"
    for _ in range(300):
        if image.is_file() and image.stat().st_size >= 1280 * 800 * 4:
            break
        time.sleep(0.5)
    else:
        raise TimeoutError(label)
    subprocess.run(["convert", image, HERE / (label + ".png")], check=True)
    tree = (out / f"windows-{label}.txt").read_text()
    (HERE / (label + ".txt")).write_text("\n".join(l.strip() for l in tree.splitlines() if
         any(word in l.lower() for word in ("help", "warn", "console", "temp", "beta", "change log", "speech", "coloring"))) + "\n")

if __name__ == "__main__":
    if sys.argv[1:] in (["launch"], ["replay"]):
        launch(sys.argv[1] == "replay")
    else:
        p = argparse.ArgumentParser()
        p.add_argument("run")
        p.add_argument("index", type=int)
        p.add_argument("label")
        p.add_argument("action", choices=("click", "ctrlf", "waittools", "showmanager", "redrawmanager",
                                         "escape", "scroll", "done", "observe"))
        p.add_argument("x", type=int, nargs="?", default=0)
        p.add_argument("y", type=int, nargs="?", default=0)
        step(**vars(p.parse_args()))
