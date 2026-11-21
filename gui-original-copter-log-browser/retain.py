"""Retain the five reviewed GUI captures and matching on-disk evidence from the run."""
import re
import shutil
import subprocess
import sys
from pathlib import Path
from run import HERE, WORK

run_id = sys.argv[1]
if not re.fullmatch("logbrowse-[a-zA-Z0-9_]{8}", run_id):
    raise ValueError(run_id)
out = WORK / "results" / run_id
for label in ("dataflash-logs", "file-name", "parsed", "gps-alt-time", "clean-time-graph"):
    subprocess.run(["convert", out / f"screen-{label}.xwd", HERE / f"{label}.png"], check=True)
for name in ("observation.log", "archive-comparison.json", "initial-user-config.xml"):
    shutil.copyfile(out / name, HERE / name)
lines = (out / "release.log").read_text(errors="replace").splitlines()
keep = ("appload time", "/evidence/downloaded.bin", "GraphItem: GPS Alt 0",
        "Graphing GPS - Alt", "GraphItem_GetList GPS Alt 0")
(HERE / "release-excerpt.log").write_text("\n".join(l for l in lines if any(k in l for k in keep)) + "\n")
# X tree holds the filename-bearing window title absent from the undecorated display.
tree = (out / "windows-clean-time-graph.txt").read_text()
(HERE / "window-titles.log").write_text("\n".join(l.strip() for l in tree.splitlines()
        if "downloaded.bin" in l or "Log Browser" in l) + "\n")
(HERE / "preview.png").unlink(missing_ok=True)
