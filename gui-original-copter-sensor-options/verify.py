"""Replay the original release's connected Copter sensor-page captures."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import runpy
import struct

ROOT = Path(__file__).resolve().parent
MAIN = runpy.run_path(str(ROOT.parent / "gui-original-copter-peripheral-views/verify.py"))
PAGES = {"adsb": "ConfigADSB", "optional": "ConfigOptional", "rangefinder": "ConfigHWRangeFinder",
         "optical-flow": "ConfigHWOptFlow"}

def sensor_snapshot(frames):
    decoder = runpy.run_path(str(ROOT.parent / "research-tools/verify-copter-parameter-views.py"))["unpack_parameters"]
    opened = False
    session = None
    data = bytearray()
    for _, sid, cid, kind, body in frames:
        if kind != 110:
            continue
        packet = body.ljust(254, b"\0")
        _, ftp_session, opcode, length, request, _, _, offset = struct.unpack_from("<HBBBBBBI", packet, 3)
        block = packet[15:15+length]
        if (sid, cid) == (255, 190) and opcode == 4:
            opened = block == b"@PARAM/param.pck?withdefaults=1"
        if not opened or (sid, cid) != (1, 1) or packet[1:3] != bytes([255, 190]):
            continue
        if (opcode, request) == (128, 4):
            session = ftp_session
        if request == 15 and ftp_session == session:
            if offset != len(data):
                raise ValueError("Missing or out-of-order packed parameters")
            if opcode == 128:
                data.extend(block)
            elif opcode == 129 and block == b"\x06":
                params = decoder(bytes(data))
                wanted = ("ADSB_TYPE", "ADSB_ENABLE", "FLOW_TYPE", "FLOW_FXSCALER", "FLOW_FYSCALER",
                          "FLOW_ORIENT_YAW", "FLOW_POS_X", "FLOW_POS_Y", "FLOW_POS_Z", "RNGFND1_TYPE")
                return {"all_parameter_count": len(params), "sensor_values": {k: params[k][0] for k in wanted if k in params}}
    raise ValueError("Incomplete parameter readback")

def collect(run, pages):
    # Reuse the same original-release identity, title, activation and heartbeat tests.
    MAIN["PAGES"].clear()
    MAIN["PAGES"].update({label: PAGES[label] for label in pages})
    result = MAIN["inspect"](run)
    frames = MAIN["TOOLS"]["packets"]
    data = gzip.decompress((run / "vehicle.tlog.gz").read_bytes())
    result["packed_parameters"] = sensor_snapshot(frames(data))
    writes = []
    sensor_params = {}
    for _, sid, cid, kind, body in frames(data):
        if sid == 255 and kind == 23:
            name = body[6:22].rstrip(b"\0").decode("ascii")
            writes.append({"name": name, "value": struct.unpack_from("<f", body)[0]})
        elif (sid, cid, kind) == (1, 1, 22):
            name = body[8:24].rstrip(b"\0").decode("ascii")
            if name.startswith(("RNGFND", "FLOW", "ADSB")):
                sensor_params[name] = struct.unpack_from("<f", body)[0]
    result["parameter_set_requests"] = writes
    result["sensor_param_value_frames"] = sensor_params
    cues = {"adsb": ("Flight Identification:", "Aircraft Registration"),
            "optional": ("The following pages are OPTIONAL",), "rangefinder": ("Distance:", "Voltage:"),
            "optical-flow": ("Scaling Factors", "Position of Sensor, relative to IMU")}
    for label in pages:
        tree = (run / f"windows-{label}.txt").read_text(errors="replace")
        if not all(cue in tree for cue in cues[label]):
            raise ValueError(f"Missing {label} control labels")
        result["pages"][label]["visual_review"] = ("blank pane, control tree populated" if label == "adsb"
                                                 else "visible and identifying content")
    if "adsb" in pages:
        later = (run / "windows-adsb-settled.txt").read_text()
        if "ADSB Type (ADSB_TYPE)" not in later:
            raise ValueError("Missing later ADSB parameter control")
        result["adsb_later_hashes"] = {name: hashlib.sha256((run / name).read_bytes()).hexdigest()
                                      for name in ("adsb-settled.png", "windows-adsb-settled.txt")}
    result["observed_activations"] = re.findall(r"(?m)^Open MissionPlanner.GCSViews.ConfigurationView\.(\w+)",
                                                 (run / "release.log").read_text(errors="replace"))
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    record = {"initial_adsb_attempt": collect(ROOT / "sensors-HXgw6hfd", ["adsb"]),
              "sensor_pages": collect(ROOT, ["optional", "rangefinder", "optical-flow", "adsb"])}
    target = ROOT / "verification.json"
    if args.check:
        if json.loads(target.read_text()) != record:
            raise SystemExit("Replay differs from the retained results")
    else:
        target.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    for run, item in record.items():
        print(f"{run}: {len(item['pages'])} captures, {item['heartbeats']} vehicle heartbeats, {item['armed_heartbeats']} armed")
