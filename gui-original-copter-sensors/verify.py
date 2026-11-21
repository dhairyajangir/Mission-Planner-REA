"""Replay the retained setup observation, including traffic from the unmodified application."""
import argparse
from bisect import bisect_left, bisect_right
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import struct

RUN = Path(__file__).resolve().parent / "sensors-FjBlM50a"
CRC_EXTRA = {0: 50, 22: 220, 23: 168, 76: 152}
PAGES = ("mandatory", "accel", "compass", "radio-input", "servo-output", "hardware-id",
         "optional", "battery", "battery-two")


def crc16(data):
    crc = 65535
    for value in data:
        tmp = (crc & 255) ^ value
        tmp ^= (tmp << 4) & 255
        crc = (crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)
    return crc


def iso(us):
    return datetime.fromtimestamp(us / 1_000_000, timezone.utc).isoformat()


def packets(data):
    pos = 0
    while pos < len(data):
        start = pos + 8
        stamp = int.from_bytes(data[pos:start], "big")
        magic, size = data[start:start + 2]
        if magic == 253:
            header = 10
            trailing = 13 if data[start + 2] & 1 else 0
            sysid, compid = data[start + 5:start + 7]
            kind = int.from_bytes(data[start + 7:start + 10], "little")
        elif magic == 254:
            header, trailing = 6, 0
            sysid, compid, kind = data[start + 3:start + 6]
        else:
            raise ValueError(f"Unexpected MAVLink header at {start}")
        body = start + header
        end = body + size
        pos = end + 2 + trailing
        if pos > len(data):
            raise ValueError("Partial tlog record")
        if kind in CRC_EXTRA:
            computed = crc16(data[start + 1:end] + bytes([CRC_EXTRA[kind]]))
            if int.from_bytes(data[end:end + 2], "little") != computed:
                raise ValueError(f"Bad CRC in {kind} at {start}")
            yield stamp, sysid, compid, kind, data[body:end]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect():
    source, = RUN.glob("*.tlog.gz")
    heartbeats = []
    armed = 0
    writes = []
    readbacks = []
    storage = []
    for timestamp, sid, cid, kind, payload in packets(gzip.decompress(source.read_bytes())):
        if kind == 0 and (sid, cid) == (1, 1):
            if payload[4:6] != bytes([2, 3]):
                raise ValueError("Unexpected vehicle/autopilot type")
            heartbeats.append(timestamp)
            armed += bool(payload[6] & 128)
        elif kind == 23 and sid == 255:
            name = payload[6:22].rstrip(b"\0").decode("ascii")
            writes.append({"utc": iso(timestamp), "name": name, "value": struct.unpack_from("<f", payload)[0]})
        elif kind == 22 and (sid, cid) == (1, 1) and payload[8:24].rstrip(b"\0") == b"BATT_VOLT_MULT":
            readbacks.append({"utc": iso(timestamp), "value": struct.unpack_from("<f", payload)[0]})
        elif kind == 76 and sid == 255 and int.from_bytes(payload[28:30], "little") == 245:
            storage.append({"utc": iso(timestamp), "param1": struct.unpack_from("<f", payload)[0]})
    if not heartbeats or heartbeats != sorted(heartbeats) or armed:
        raise ValueError("Missing, unordered or armed vehicle heartbeats")
    actions = {label: int(datetime.fromisoformat(t[:-1] + "+00:00").timestamp()) * 1_000_000
               for t, label in re.findall(r"(?m)^(\S+Z): click \([^)]*\) label ([a-z0-9-]+)$",
                                          (RUN / "observation.log").read_text())}
    cases = {}
    for label in PAGES:
        went = actions[label]
        left = bisect_right(heartbeats, went) - 1
        right = bisect_left(heartbeats, went + 6_000_000)
        if left < 0 or right >= len(heartbeats) or went - heartbeats[left] > 3_000_000:
            raise ValueError(f"Missing heartbeat at {label}")
        if heartbeats[right] - (went + 6_000_000) > 3_000_000:
            raise ValueError(f"Missing following heartbeat at {label}")
        tree = RUN / f"windows-{label}.txt"
        if "ArduCopter V4.8.0-dev" not in tree.read_text():
            raise ValueError(f"Missing connected window at {label}")
        cases[label] = {"click_utc": iso(went), "disarmed_before_click": iso(heartbeats[left]),
                        "disarmed_after_nominal_capture": iso(heartbeats[right]),
                        "screenshot_sha256": digest(RUN / (label + ".png")), "tree_sha256": digest(tree)}
    arch = json.loads((RUN / "archive-comparison.json").read_text())
    if arch["matching"] != arch["release_files"] or arch["missing"] or arch["changed"]:
        raise ValueError("Release file changed")
    return {"vehicle_heartbeats": len(heartbeats), "armed_heartbeats": armed,
            "first_heartbeat_utc": iso(heartbeats[0]), "last_heartbeat_utc": iso(heartbeats[-1]),
            "gcs_param_set": writes, "vehicle_batt_volt_mult_param_value": readbacks,
            "gcs_preflight_storage": storage, "tlog_gz_sha256": digest(source),
            "archive_sha256": arch["archive_sha256"], "archive_matching_files": arch["matching"], "captures": cases}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = collect()
    out = RUN / "verification.json"
    if args.check:
        if json.loads(out.read_text()) != result:
            raise SystemExit("Capture replay differs from retained verification")
    else:
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(result['captures'])} pages, {result['vehicle_heartbeats']} disarmed heartbeat samples")
