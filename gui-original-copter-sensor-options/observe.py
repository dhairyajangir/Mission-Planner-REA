"""View a named setup-page capture from a private Ubuntu-E session, or finish it."""
import argparse
import gzip
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("run")
ap.add_argument("label")
ap.add_argument("step", type=int)
ap.add_argument("point", type=int, nargs="*")
args = ap.parse_args()
if not re.fullmatch(r"sensors-[a-zA-Z0-9]{8}", args.run) or not re.fullmatch(r"[a-z0-9-]+", args.label):
    ap.error("Invalid capture or label")
dest = Path(__file__).resolve().parent
repo = dest.parent
guest = Path("/tmp/mission-planner-original-gui-nov21/results") / args.run
if args.label in {"finish", "startup-stop"}:
    instruction = "done 0 finished"
elif args.step == 0 and args.label == "startup":
    instruction = None
else:
    if len(args.point) != 2 or not (0 <= args.point[0] < 1280 and 0 <= args.point[1] < 800):
        ap.error("Expected a point within the display")
    instruction = f"{args.point[0]} {args.point[1]} {args.label}"
if instruction:
    if not 1 <= args.step <= 40:
        ap.error("Step must be between 1 and 40")
    with (guest / f"action-{args.step}").open("x") as handle:
        print(instruction, file=handle)
if args.label in {"finish", "startup-stop"}:
    for _ in range(60):
        if (guest / "telemetry").is_dir() and ".config" in (guest / "observation.log").read_text().splitlines():
            break
        time.sleep(1)
    else:
        raise SystemExit("Guest did not finalize evidence")
    if args.label == "startup-stop":
        dest = dest / "startup-attempts" / args.run
        dest.mkdir(parents=True, exist_ok=True)
        subprocess.run(["convert", str(guest / "screen-startup.xwd"), str(dest / "startup.png")], check=True)
        shutil.copyfile(guest / "windows-startup.txt", dest / "windows-startup.txt")
    for name in ("capture.sh", "release.log", "observation.log", "copter.log", "initial-user-config.xml"):
        shutil.copyfile(guest / name, dest / name)
    logs = list((guest / "telemetry").glob("*.tlog"))
    if not logs and args.label != "startup-stop":
        raise SystemExit("No vehicle telemetry in connected observation")
    if logs:
        log, = logs
        with log.open("rb") as source, gzip.open(dest / "vehicle.tlog.gz", "wb") as output:
            shutil.copyfileobj(source, output)
    subprocess.run([sys.executable, str(repo / "gui-original-mono-evidence-20261122/runtime/compare_archive.py"),
                    str(repo / "mission-planner-portable.zip"), (guest / "extracted-path.txt").read_text().strip(),
                    str(dest / "archive-comparison.json")], check=True)
else:
    raw = guest / f"screen-{args.label}.xwd"
    for _ in range(240):
        if raw.is_file() and raw.stat().st_size >= 1280 * 800 * 4:
            break
        time.sleep(0.5)
    else:
        raise SystemExit("Guest did not produce the requested capture")
    keep = args.label in {"startup", "adsb", "adsb-settled", "rangefinder", "optical-flow", "optional", "final-hud"}
    # Menu navigation aids stay in the temporary guest, the three reviewed pages are retained.
    target = dest if keep else guest
    subprocess.run(["convert", str(raw), str(target / (args.label + ".png"))], check=True)
    if keep:
        shutil.copyfile(guest / f"windows-{args.label}.txt", dest / f"windows-{args.label}.txt")
    else:
        shutil.copyfile(target / (args.label + ".png"), dest / "navigation-preview.png")
