"""Open the original plugin manager using the existing disconnected Mono fixture."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from xml.etree import ElementTree

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "gui-original-mono-evidence-20261122"
ARCHIVE = HERE.parent.parent / "mission-planner-portable.zip"
WORK = Path("/tmp/mission-planner-original-gui-nov21")

def run():
    out = Path(tempfile.mkdtemp(prefix="pluginui-", dir=WORK / "results"))
    app = Path(tempfile.mkdtemp(prefix="app-pluginui-", dir=WORK))
    print(out.name, flush=True)
    subprocess.run(["unzip", "-qo", ARCHIVE, "-d", app], check=True)
    startup = (BASE / "disconnected/capture.sh").read_text().split("# An operator reads")[0]
    (out / "capture.sh").write_text(startup + (HERE / "actions.sh").read_text())
    root = WORK / "root"
    result = subprocess.run([root / "usr/bin/bwrap", "--die-with-parent", "--new-session",
        "--unshare-all", "--cap-drop", "ALL", "--clearenv", "--ro-bind", root, "/", "--proc", "/proc",
        "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/home/test", "--tmpfs", "/var/lib/xkb",
        "--bind", app, "/opt/mp", "--bind", out, "/evidence", "--chdir", "/opt/mp",
        "--setenv", "HOME", "/home/test", "--setenv", "USER", "test", "--setenv", "LANG", "C.UTF-8",
        "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "XDG_CONFIG_HOME", "/home/test/.config",
        "--setenv", "XDG_DATA_HOME", "/home/test/.local/share", "--setenv", "DISPLAY", ":58",
        "--setenv", "SKIP_STARTUP_PLUGINS", "2", "--setenv", "LIBGL_ALWAYS_SOFTWARE", "1",
        "/bin/bash", "/evidence/capture.sh"])
    subprocess.run([sys.executable, BASE / "runtime/compare_archive.py", ARCHIVE, app, HERE / "archive-comparison.json"], check=True)
    for name in ("observation.log", "initial-user-config.xml"):
        if (out / name).exists():
            shutil.copyfile(out / name, HERE / name)
    compare_settings(out / "initial-user-config.xml", out / "final-user-config.xml")
    for label in ("startup", "manager-open", "manager-settled"):
        frame = out / f"screen-{label}.xwd"
        if frame.exists():
            subprocess.run(["convert", frame, HERE / (label + ".png")], check=True)
    tree = (out / "windows-manager-settled.txt")
    if tree.exists():
        lines = tree.read_text().splitlines()
        start = next((i for i,l in enumerate(lines) if re.match(r'^     0x[\da-f]+ "PluginManager":',l)),None)
        if start is not None:
            end = next((i for i in range(start+1,len(lines)) if re.match(r"^     0x[\da-f]+ ",lines[i])),len(lines))
            (HERE / "manager-tree.txt").write_text("\n".join(lines[start:end]) + "\n")
    lines = (out / "release.log").read_text(errors="replace").splitlines()
    keys = ("appload time", "mainv2_keydown", "pluginmanager", "pluginui", "disabledplugin",
            "skipping plugin", "plugin disabled", "pluginloader", "loading plugin", "plugin - ")
    (HERE / "release-excerpt.log").write_text("\n".join(l for l in lines if any(k in l.lower() for k in keys)) + "\n")
    result.check_returncode()

def compare_settings(before, after):
    result = {}
    for key, path in (("before", before), ("after", after)):
        data = path.read_bytes()
        root = ElementTree.fromstring(data)
        result[key] = {
            "xml_sha256": hashlib.sha256(data).hexdigest(),
            "keys": sorted(child.tag for child in root),
            "disabled_plugins": root.findtext("DisabledPlugins").split(";"),
        }
    (HERE / "settings-comparison.json").write_text(json.dumps(result, indent=2) + "\n")

if __name__ == "__main__":
    run()
