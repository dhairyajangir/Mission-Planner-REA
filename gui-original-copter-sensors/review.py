"""Observe or drive one named offline guest and retain its resulting screen."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument("run")
parser.add_argument("screen")
parser.add_argument("--action", nargs=3, type=int, metavar=("STEP", "X", "Y"))
args = parser.parse_args()
if not re.fullmatch(r"sensors-[a-zA-Z0-9]{8}", args.run) or not re.fullmatch(r"[a-z0-9-]+", args.screen):
    raise SystemExit("invalid run or screen")
runtime = Path("/tmp/mission-planner-original-gui-nov21/results") / args.run
dest = Path(__file__).resolve().parent / args.run
dest.mkdir(exist_ok=True)
if args.action:
    step, x, y = args.action
    if not (1 <= step <= 40 and 0 <= x < 1280 and 0 <= y < 800):
        raise SystemExit("invalid action")
    action = runtime / f"action-{step}"
    with action.open("x") as handle:
        print(x, y, args.screen, file=handle)

raw = runtime / f"screen-{args.screen}.xwd"
for _ in range(120):
    if raw.exists() and raw.stat().st_size >= 1280 * 800 * 4:
        break
    time.sleep(0.5)
else:
    raise SystemExit(f"Screen not produced: {args.screen}")
subprocess.run(["convert", str(raw), str(dest / f"{args.screen}.png")], check=True)
for name in ("observation.log", "release.log", "xvfb.log", "display.txt", f"windows-{args.screen}.txt", "capture.sh"):
    shutil.copyfile(runtime / name, dest / name)
print(args.run, args.screen, (dest / f"{args.screen}.png").stat().st_size, "PNG bytes")
