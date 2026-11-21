"""Record a normal UI action and collect the resulting screen from one isolated PLAN guest."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("run", type=str)
parser.add_argument("label")
parser.add_argument("output", type=Path)
parser.add_argument("--action", nargs=4, metavar=("STEP", "VERB", "X", "Y"))
args = parser.parse_args()
if not re.fullmatch("plan-[a-zA-Z0-9]{8}", args.run) or not re.fullmatch("[a-z0-9-]+", args.label):
    parser.error("invalid run or label")
run = Path("/tmp/mission-planner-original-gui-nov21/results") / args.run
dest = args.output
dest.mkdir(parents=True, exist_ok=True)
if args.action:
    step, verb, x, y = args.action
    if not (1 <= int(step) <= 36 and verb in {"click", "right", "fixture", "output", "enter", "escape", "finish"}
            and 0 <= int(x) < 1280 and 0 <= int(y) < 800):
        parser.error("invalid action")
    with (run / ("action-" + step)).open("x") as action:
        print(verb, x, y, args.label, file=action)
    if verb == "finish":
        raise SystemExit(0)
raw = run / (args.label + ".xwd")
for _ in range(180):
    if raw.exists() and raw.stat().st_size >= 1280 * 800 * 4:
        break
    time.sleep(1)
else:
    raise SystemExit("Timed out waiting for " + args.label)
subprocess.run(["convert", raw, "-strip", dest / (args.label + ".png")], check=True)
for filename in [args.label + "-tree.txt", "observation.log", "release.log", "initial-user-config.xml",
                 "input.waypoints"]:
    shutil.copyfile(run / filename, dest / filename)
print(args.label)
