"""Repeat the observed load sequence only when the expected controls occupy the captured positions."""
import argparse
from pathlib import Path
import re
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("run")
args = parser.parse_args()
if not re.fullmatch("plan-[a-zA-Z0-9]{8}", args.run):
    parser.error("invalid run")
guest = Path("/tmp/mission-planner-original-gui-nov21/results") / args.run
steps = [
    ("startup", '"Mission Planner 1.3.83 build 1.3.9384.38258": ()  1101x577+86+98', "click 158 120 plan"),
    ("plan", '"Load File": ()  115x23+3+3  +1063+350', "click 1112 362 load-dialog"),
    ("load-dialog", '"File name:": ()  70x21+101+326  +460+520', "click 615 530 filename-focus"),
    ("filename-focus", '"File name:": ()  70x21+101+326  +460+520', "fixture 0 0 fixture-name"),
    ("fixture-name", '"Open": ()  75x23+474+326  +833+520', "click 868 530 load-result"),
    ("load-result", '"Yes": ()  75x23+91+76  +113+98', "click 146 108 accepted-home"),
    ("accepted-home", '"Save File": ()  115x23+3+32  +1063+379', "click 1115 390 save-dialog"),
]
for i, (screen, anchor, action) in enumerate(steps, 1):
    xwd = guest / (screen + ".xwd")
    for _ in range(180):
        if xwd.exists() and xwd.stat().st_size >= 1280 * 800 * 4:
            break
        time.sleep(1)
    tree = (guest / (screen + "-tree.txt")).read_text()
    if anchor not in tree or (screen == "accepted-home" and "Loaded plan-readback.waypoints" not in tree):
        raise SystemExit("Changed dialog or window geometry at " + screen)
    with (guest / ("action-" + str(i))).open("x") as command:
        print(action, file=command)
    print(screen + " -> " + action, flush=True)
