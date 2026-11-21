"""Verify the connected original-window tuning and FFT page observations offline."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import runpy
import struct

ROOT = Path(__file__).resolve().parent
SHARED = runpy.run_path(str(ROOT.parent / "gui-original-copter-peripheral-views/verify.py"))
PAGES = {"initial": "ConfigInitialParams", "fft": "ConfigFFT"}

def collect():
    SHARED["PAGES"].clear()
    SHARED["PAGES"].update(PAGES)
    result = SHARED["inspect"](ROOT)
    activation = re.findall(r"(?m)^Open MissionPlanner.GCSViews.ConfigurationView\.(\w+)",
                            (ROOT / "release.log").read_text(errors="replace"))
    result["setup_activations"] = activation
    if activation != ["ConfigMandatory", "ConfigInitialParams", "ConfigOptional", "ConfigFFT"]:
        raise ValueError("Unexpected setup navigation")
    for name, cues in (("initial", ("Battery Chemistry", "Calculate Initial Parameters")),
                       ("fft-settled", ("1024", "IMU1", "IMU_RAW and IMU_FAST", "FFT Setup"))):
        text = (ROOT / f"windows-{name}.txt").read_text(errors="replace")
        if not all(cue.lower() in text.lower() for cue in cues):
            raise ValueError(f"Missing named controls in {name}")
    result["reviewed_screens"] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                                  ("initial.png", "fft-settled.png", "windows-fft-settled.txt", "final-hud-settled.png")}
    writes = []
    for timestamp, sid, _, kind, payload in SHARED["TOOLS"]["packets"](gzip.decompress((ROOT / "vehicle.tlog.gz").read_bytes())):
        if sid == 255 and kind == 23:
            writes.append({"time_us": timestamp, "name": payload[6:22].rstrip(b"\0").decode("ascii"),
                           "value": struct.unpack_from("<f", payload)[0]})
    result["gcs_parameter_set_requests"] = writes
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = collect()
    path = ROOT / "verification.json"
    if args.check:
        if result != json.loads(path.read_text()):
            raise SystemExit("Retained record differs from replay")
    else:
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(result["setup_activations"], result["heartbeats"], "vehicle heartbeat samples")
