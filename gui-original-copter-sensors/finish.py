"""Close one completed guest observation and retain its logs and archive comparison."""
import argparse
import gzip
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("run")
parser.add_argument("next_step", type=int)
args = parser.parse_args()
if not re.fullmatch(r"sensors-[a-zA-Z0-9]{8}", args.run) or not 1 <= args.next_step <= 40:
    parser.error("Invalid run or step")
lane = Path(__file__).resolve().parent
repo = lane.parent
guest = Path("/tmp/mission-planner-original-gui-nov21/results") / args.run
out = lane / args.run
with (guest / f"action-{args.next_step}").open("x") as handle:
    print("done 0 finished", file=handle)
for _ in range(30):
    if (guest / "telemetry").exists() and ".config" in (guest / "observation.log").read_text().splitlines():
        break
    time.sleep(1)
else:
    raise SystemExit("Guest did not finish collecting observation files")
for name in ["initial-user-config.xml", "observation.log", "release.log", "copter.log", "extracted-path.txt"]:
    shutil.copyfile(guest / name, out / name)
for tlog in (guest / "telemetry").glob("*.tlog"):
    with tlog.open("rb") as source, gzip.open(out / (tlog.name + ".gz"), "wb") as dest:
        shutil.copyfileobj(source, dest)
extracted = (out / "extracted-path.txt").read_text().strip()
subprocess.run([sys.executable, str(repo / "gui-original-mono-evidence-20261122/runtime/compare_archive.py"),
                str(repo / "mission-planner-portable.zip"), extracted, str(out / "archive-comparison.json")], check=True)
