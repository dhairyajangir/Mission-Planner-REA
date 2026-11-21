"""Independently compare GPS[0].Alt graph points with the retained DataFlash records."""
import argparse
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "mission-planner-portable"
CAPTURE = ROOT / "sitl-evidence/copter-log-gps-graph"
LOG = ROOT / "sitl-evidence/nonempty-log-probe/downloaded.bin"
GPS_FMT = struct.Struct("<QBBIHBhiiiffffB")
GPS_EPOCH = datetime(1980, 1, 6, tzinfo=timezone.utc)
XDATE_EPOCH = datetime(1899, 12, 30)


def samples():
    data = LOG.read_bytes()
    lengths = {128: 89}
    gps_type = None
    offset = line = 0
    rows = []
    while offset < len(data):
        if data[offset:offset + 2] != b"\xa3\x95":
            raise ValueError(f"Bad header at {offset}")
        kind = data[offset + 2]
        if kind == 128:
            number, length, name, fmt, columns = struct.unpack_from("<BB4s16s64s", data, offset + 3)
            lengths[number] = length
            if name.rstrip(b"\0") == b"GPS":
                if (fmt.rstrip(b"\0") != b"QBBIHBcLLeffffB" or GPS_FMT.size + 3 != length or
                    columns.split(b",")[:10] != b"TimeUS,I,Status,GMS,GWk,NSats,HDop,Lat,Lng,Alt".split(b",")):
                    raise ValueError("Unexpected GPS schema")
                gps_type = number
        if kind == gps_type:
            gps = GPS_FMT.unpack_from(data, offset + 3)
            if gps[1] == 0:
                rows.append((line, gps[0], gps[2], gps[3], gps[4], gps[9]))
        offset += lengths[kind]
        line += 1
    if len(rows) != 391:
        raise ValueError("Unexpected GPS instance 0 record count")
    return rows


def verify(path, zone):
    with path.open(encoding="ascii", newline="") as stream:
        all_points = list(csv.DictReader(stream))
    rows = samples()
    anchor = next(r for r in rows if r[2] >= 3)
    # The captured 2026 log uses a GPS-UTC offset of 18 seconds.
    absolute = GPS_EPOCH + timedelta(weeks=anchor[4], milliseconds=anchor[3], seconds=-18)
    local_anchor = absolute.astimezone(zone).replace(tzinfo=None)
    errors = []
    if len(all_points) != 2 * len(rows):
        raise ValueError("Unexpected curve point count")
    for axis in ("x_time", "x_line"):
        points = [p for p in all_points if p["axis"] == axis]
        if len(points) != len(rows):
            raise ValueError(f"Missing graph axis {axis}")
        for i, (point, (line, usec, _, _, _, alt_cm)) in enumerate(zip(points, rows)):
            if int(point["index"]) != i or Decimal(point["y"]) * 100 != alt_cm:
                raise ValueError(f"Altitude or index differs at {axis} point {i}")
            if axis == "x_line":
                if Decimal(point["x"]) != line:
                    raise ValueError(f"Line coordinates differ at point {i}")
            else:
                expected = local_anchor + timedelta(microseconds=usec - (anchor[1] // 1000) * 1000)
                actual = XDATE_EPOCH + timedelta(days=float(point["x"]))
                errors.append(round((actual - expected).total_seconds() * 1_000_000))
    if max(map(abs, errors)) > 50:
        raise ValueError("Time-axis discrepancy exceeds 50 microseconds")
    return {"samples_per_axis": len(rows), "first_line": rows[0][0], "last_line": rows[-1][0],
            "anchor_utc": absolute.isoformat(), "time_error_us_range": [min(errors), max(errors)],
            "altitude_cm_counts": {str(alt): sum(r[-1] == alt for r in rows) for alt in sorted({r[-1] for r in rows})}}


def replay():
    with tempfile.TemporaryDirectory() as scratch:
        temp = Path(scratch)
        exe = temp / "CopterLogGraphProbe.exe"
        compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
        subprocess.run([compiler, "/nologo", "/r:System.Windows.Forms.dll", "/r:Microsoft.CSharp.dll",
                        "/out:" + str(exe), ROOT / "research-tools/CopterLogGraphProbe.cs"], check=True)
        shutil.copyfile(RELEASE / "MissionPlanner.exe.config", str(exe) + ".config")
        generated = temp / "points.csv"
        run = subprocess.run([exe, RELEASE, LOG, generated, temp], cwd=temp, env=dict(os.environ, TEMP=scratch, TMP=scratch),
                             capture_output=True, text=True, timeout=75)
        if run.returncode or any(f"{axis} GPS[0].Alt points=391" not in run.stdout for axis in ("x_line", "x_time")):
            raise RuntimeError(run.stderr or run.stdout)
        return verify(generated, None)  # Time axis follows the system's local timezone.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", action="store_true", help="rerun the .NET Framework graph probe on Windows")
    args = parser.parse_args()
    components = {}
    with zipfile.ZipFile(ROOT / "mission-planner-portable.zip") as archive:
        for name in ("MissionPlanner.exe", "MissionPlanner.Utilities.dll", "ZedGraph.dll", "MissionPlanner.exe.config"):
            data = (RELEASE / name).read_bytes()
            if data != archive.read(name):
                raise ValueError(f"Release ZIP mismatch: {name}")
            components[name] = hashlib.sha256(data).hexdigest()
    points = CAPTURE / "points.csv"
    summary = {"input_sha256": hashlib.sha256(LOG.read_bytes()).hexdigest(),
               "points_sha256": hashlib.sha256(points.read_bytes()).hexdigest(),
               "release_sha256": components, "recorded_local_offset_minutes": 330,
               "retained": verify(points, timezone(timedelta(minutes=330)))}
    if args.replay:
        summary["replay"] = replay()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
