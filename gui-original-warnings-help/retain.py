"""Retain control trees and application identity records from one completed guest."""
from pathlib import Path
import argparse
import re
from run import HERE, WORK

p = argparse.ArgumentParser()
p.add_argument("run")
p.add_argument("--initial", action="store_true")
p.add_argument("--manager", default="manager-open")
a = p.parse_args()
if not re.fullmatch(r"warnhelp-[a-z0-9_]{8}", a.run) or not re.fullmatch(r"[a-z-]+", a.manager):
    raise ValueError("Invalid capture")
out = WORK / "results" / a.run
dest = HERE / "initial-attempt" if a.initial else HERE
keep = ("appload time", "Open MissionPlanner.GCSViews.Help", "Open MissionPlanner.temp",
        "Open MissionPlanner.Controls.SerialOutputMD", "Open MissionPlanner.Warnings")
(dest / "release-excerpt.log").write_text("\n".join(l for l in (out/"release.log").read_text(errors="replace").splitlines()
        if any(k in l for k in keep)) + "\n")
tree = (out / f"windows-{a.manager}.txt").read_text().splitlines()
start = next(i for i, line in enumerate(tree) if re.match(r'^     0x[\da-f]+ "Warning Manager":', line))
end = next((i for i in range(start+1, len(tree)) if re.match(r"^     0x[\da-f]+ ", tree[i])), len(tree))
(dest / "manager-tree.txt").write_text("\n".join(tree[start:end]) + "\n")
if not a.initial:
    tree = (out / "windows-help-page.txt").read_text().splitlines()
    (dest / "help-controls.txt").write_text("\n".join(l.strip() for l in tree if any(t in l for t in
        ('"Check for Updates"', '"Check for BETA Updates"', '"Change Log"', '"Show Console Window (restart)"'))) + "\n")
