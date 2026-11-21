"""Verify the stock CONFIG menu, visible page evidence, and private simulator traffic."""
import argparse
from collections import Counter
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import re
import runpy

ROOT = Path(__file__).resolve().parent
SHARED = runpy.run_path(str(ROOT.parent / "gui-original-copter-peripheral-views/verify.py"))
MENU = ["GeoFence", "Basic Tuning", "Extended Tuning", "MAVFtp", "User Params", "Full Parameter List", "Planner"]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def inspect(run, extra):
    SHARED["PAGES"].clear()
    result = SHARED["inspect"](run)
    raw = (run / "windows-config.txt").read_text(errors="replace")
    menu = re.findall(r'(?m)^\s*0x\w+ "([^"]+)": \(\)  172x30\+0\+\d+  \+86\+\d+\s*$', raw)
    if menu != MENU:
        raise ValueError(f"Different CONFIG menu: {menu}")
    if "ArduCopter V4.8.0-dev" not in raw:
        raise ValueError("Connected vehicle absent")
    log = (run / "release.log").read_text(errors="replace")
    result["menu"] = menu
    result["opened"] = re.findall(r"(?m)^Open (MissionPlanner\.[^\r\n]+)", log)
    if any("ConfigFriendlyParams" in entry for entry in result["opened"]):
        raise ValueError("Unexpected friendly-page activation")
    ticks = {label: datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
             for ts, label in re.findall(r"(?m)^(\S+Z): click \([^)]*\) label (\S+)$", (run / "observation.log").read_text())}
    wire = gzip.decompress((run / "vehicle.tlog.gz").read_bytes())
    tx = list(SHARED["outbound_frames"](wire))
    beats = []
    ftp = []
    commands = []
    for us, sid, cid, kind, payload in SHARED["TOOLS"]["packets"](wire):
        if (sid,cid,kind) == (1,1,0):
            if payload[6] & 128:
                raise ValueError("Armed heartbeat")
            beats.append(us / 1_000_000)
        if sid == 255 and kind == 110:
            msg = payload.ljust(254, b"\0")
            opcode = msg[6]
            path = msg[15:15+msg[7]].rstrip(b"\0").decode("ascii") if opcode in (3, 4) else None
            ftp.append((us/1_000_000, opcode, path))
        if sid == 255 and kind in (75, 76):
            commands.append((us/1_000_000, int.from_bytes(payload[28:30], "little")))
    result["selections"] = {}
    for label in ["config", *extra]:
        start = ticks[label]
        if not (any(start-3 <= t <= start for t in beats) and any(start+5 <= t <= start+8 for t in beats)):
            raise ValueError(f"Missing heartbeat near {label}")
        result["selections"][label] = {"screen_sha256": digest(run / (label + ".png")),
            "tree_sha256": digest(run / ("windows-" + label + ".txt")),
            "outgoing_ids_first_6s": dict(Counter(str(k) for t,k in tx if start <= t < start+6)),
            "command_ids_first_6s": dict(Counter(str(c) for t,c in commands if start <= t < start+6)),
            "ftp_requests_first_6s": [{"opcode": op, "path": path} for t,op,path in ftp if start <= t < start+6]}
    if extra:
        for activation in ("MissionPlanner.Controls.MavFTPUI MAVFtp", "MissionPlanner.GCSViews.ConfigurationView.ConfigArducopter Extended Tuning"):
            if activation not in result["opened"]:
                raise ValueError(f"Missing activation: {activation}")
        for label in ("extended", "extended-settled"):
            tree = (run / f"windows-{label}.txt").read_text()
            if not all(f'"{cue}"' in tree for cue in ("Lock Pitch and Roll Values", "Rate Roll", "Rate Pitch", "Rate Yaw")):
                raise ValueError(f"Missing tuning controls in {label}")
        requests = result["selections"]["mavftp"]["ftp_requests_first_6s"]
        if not any(r["opcode"] == 3 for r in requests):
            raise ValueError("Missing directory-list request on selecting MAVFtp")
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = {"first_menu": inspect(ROOT / "sensors-5eLzDluK", []),
            "completed_retry": inspect(ROOT, ["mavftp", "extended", "extended-settled"])}
    path = ROOT / "verification.json"
    if args.check:
        if json.loads(path.read_text()) != data:
            raise SystemExit("Retained evidence differs")
    else:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print({n: d["heartbeats"] for n,d in data.items()})
