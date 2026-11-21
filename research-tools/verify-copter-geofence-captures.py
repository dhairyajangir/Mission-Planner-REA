"""Cross-check the nine archived Copter fence cases without starting a simulator."""
import argparse
import csv
import json
import math
import re
from itertools import groupby
from pathlib import Path


# Label, first breach response (None for avoidance), number of saved positions.
BATCHES = {
    "circle/fence-circle-result-rtl-land-brake.json": [
        ("rtl", "RTL", 1722), ("land", "LAND", 1326), ("brake", "BRAKE", 2302)],
    "circle/fence-circle-result-rtl-margin8-notify-avoid-on-margin2-avoid-on-margin8.json": [
        ("rtl-margin8-notify", "RTL", 1717), ("avoid-on-margin2", None, 2023),
        ("avoid-on-margin8", None, 2039)],
    "polygon/fence-polygon-result.json": [
        ("poly-rtl", "RTL", 1649), ("poly-brake-recover", "BRAKE", 2256),
        ("poly-brake-opt1-locked", "BRAKE", 2068)],
}


def require(ok, description):
    if not ok:
        raise ValueError(description)


def check_case(folder, shape, label, response, row_count, summary):
    notes = (folder / (label + "-notes.txt")).read_text(encoding="utf-8")
    with (folder / (label + "-track.csv")).open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == row_count, "position record count")
    require("case " + label + ":" in notes.splitlines()[0], "notes label")
    times = [float(row["seconds"]) for row in rows]
    require(all(math.isfinite(t) for t in times) and times == sorted(times), "time order")
    distances = [float(row["dist_from_home_m"]) for row in rows]
    for row, distance in zip(rows, distances):
        position_radius = math.hypot(float(row["north_m"]), float(row["east_m"]))
        # Two coordinates and the radius were each rounded independently to 0.1 m.
        require(abs(position_radius - distance) <= 0.121, "radius disagrees with position")
    peak = max(distances)
    require(peak == summary["max_dist_overall"], "peak disagrees with summary")

    modes = [key for key, _ in groupby(row["mode"] for row in rows)]
    heartbeats = re.findall(r"HEARTBEAT mode=(\w+) armed=(True|False)", notes)
    require(("LOITER", "True") in heartbeats and "LOITER" in modes, "missing armed LOITER")
    require(heartbeats[-1] == (modes[-1], "False") and summary["final_mode"] == modes[-1]
            and summary["final_armed"] is False, "final disarmed heartbeat")
    fence_status = re.findall(r"FENCE_STATUS breach_status=(\d+) count=(\d+) type=(\d+)", notes)
    require(fence_status[0] == ("0", "0", "0"), "missing initial clear fence status")
    breaches = [values for values in fence_status if values[0] != "0"]
    next_mode = modes[modes.index("LOITER") + 1]
    if response:
        require(breaches == [("1", "1", "3")], "lateral breach status")
        require("vehicle: " + shape.capitalize() + " fence breached" in notes, "missing shape message")
        require(next_mode == response == summary["mode_after_breach"]
                and (response, "True") in heartbeats, "breach response")
    else:
        require(not breaches and "fence breached" not in notes, "unexpected breach")
        require(modes[modes.index("LOITER"):] == ["LOITER", "LAND"]
                and summary["mode_end_of_hold"] == "LOITER", "avoidance mode")
        require("holding pitch forward 45 s total" in notes and "switching to LAND to finish" in notes,
                "missing observation or harness landing")
        require(peak == summary["FENCE_RADIUS"] - summary["FENCE_MARGIN"], "avoidance radius")


def verify_captures(root):
    for batch, cases in BATCHES.items():
        shape, filename = batch.split("/")
        folder = root / ("copter-fence-breach-" + shape)
        results = json.loads((folder / filename).read_text(encoding="utf-8"))
        expected = sorted(label for label, _, _ in cases)
        require(sorted(case["label"] for case in results) == expected, filename + " case labels")
        by_label = {case["label"]: case for case in results}
        for label, mode, count in cases:
            try:
                check_case(folder, shape, label, mode, count, by_label[label])
            except (ValueError, KeyError, IndexError) as error:
                raise ValueError(label + ": " + str(error)) from error


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path,
                        default=Path(__file__).resolve().parents[1] / "sitl-evidence")
    try:
        verify_captures(parser.parse_args().evidence_root)
    except ValueError as error:
        raise SystemExit("FAIL " + str(error)) from error
    print("PASS 9 Copter fence captures, 17102 position records, 7 breaches and 2 avoidance cases")
