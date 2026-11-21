"""Verify retained evidence offline; the GUI and simulator are never launched."""
import collections
import gzip
import hashlib
import json
from pathlib import Path
import struct

from PIL import Image

ROOT = Path(__file__).resolve().parent
EXTRA_CRC = {0: 50, 22: 220, 23: 168, 65: 118}
BASELINE = (7, 9, 6, 3, 5, 0)
SAVED = (9, 9, 6, 3, 5, 0)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def crc_x25(data):
    crc = 0xffff
    for byte in data:
        mixed = (crc & 0xff) ^ byte
        mixed ^= (mixed << 4) & 0xff
        crc = (crc >> 8) ^ (mixed << 8) ^ (mixed << 3) ^ (mixed >> 4)
    return crc


def frames(data):
    # TLOG adds 8-byte timestamps between packets. Select only actual v1/v2
    # packets whose known message CRC verifies; skip timestamps and other types.
    pos = 0
    while pos + 8 <= len(data):
        start = pos
        pos += 1
        magic = data[start]
        if magic not in (0xfe, 0xfd):
            continue
        v2 = magic == 0xfd
        end_header = start + (10 if v2 else 6)
        if end_header > len(data):
            continue
        msgid = int.from_bytes(data[start + 7:end_header], "little") if v2 else data[start + 5]
        if msgid not in EXTRA_CRC:
            continue
        end = end_header + data[start + 1]
        if end + 2 > len(data):
            continue
        expected_crc = int.from_bytes(data[end:end + 2], "little")
        if crc_x25(data[start + 1:end] + bytes([EXTRA_CRC[msgid]])) != expected_crc:
            continue
        seq = start + (4 if v2 else 2)
        yield msgid, tuple(data[seq + 1:seq + 3]), data[seq], data[end_header:end]
        pos = end + 2 + (13 if v2 and data[start + 2] & 1 else 0)


def observer(step, expected_slots):
    decoded = []
    seen = collections.Counter()
    expected = {"MAV_SYSID": 1, "FRAME_CLASS": 1, "FLTMODE_CH": 5}
    expected.update({f"FLTMODE{n}": mode for n, mode in enumerate(expected_slots, 1)})
    beats = 0
    for msg, sender, seq, raw in frames((ROOT / f"serial1-{step}.bin").read_bytes()):
        if sender != (1, 1):
            continue
        if msg == 0:
            mode, vehicle, autopilot, base, _, _ = struct.unpack("<IBBBBB", raw.ljust(9, b"\0"))
            require((vehicle, autopilot, mode, base & 128) == (2, 3, 0, 0), "unexpected aircraft state")
            decoded.append(dict(kind="HEARTBEAT", seq=seq, vehicle=vehicle, autopilot=autopilot,
                                base_mode=base, custom_mode=mode, armed=False))
            beats += 1
        if msg == 22:
            value, count, index, key, _ = struct.unpack("<fHH16sB", raw.ljust(25, b"\0"))
            key = key.split(b"\0")[0].decode("ascii")
            if key in expected:
                require(value == expected[key], f"stage {step} {key} returned {value}")
                seen[key] += 1
                decoded.append(dict(kind="PARAM_VALUE", seq=seq, name=key, value=value, index=index, count=count))
    require(beats >= 2 and set(seen) == set(expected) and min(seen.values()) >= 2, "missing repeat read or heartbeat")
    recorded = json.loads((ROOT / f"serial1-{step}.json").read_text())
    require(recorded["records"] == decoded, "pymavlink export differs from independent wire decode")
    print(f"stage {step}: {expected_slots}, {beats} vehicle heartbeats, disarmed")


def label(name, offset=0):
    # Match actual rasterized combo text, which Mono omits from X11 window names.
    with Image.open(ROOT / (name + ".png")) as img:
        require(img.size == (1280, 800), "wrong display size")
        return img.convert("RGB").crop((372, 201 + offset, 451, 220 + offset)).tobytes()


def verify():
    lines = (ROOT / "manifest.sha256").read_text().splitlines()
    inventory = set()
    for line in lines:
        digest, name = line.split("  ", 1)
        inventory.add(name)
        require(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, f"hash mismatch: {name}")
    require(inventory == {p.name for p in ROOT.iterdir() if p.is_file() and p.name != "manifest.sha256"},
            "capture file inventory differs from manifest")
    for step, slots in enumerate((BASELINE, BASELINE, SAVED, BASELINE), 1):
        observer(step, slots)
    circle, land = label("initial-modes"), label("initial-modes", 25)
    require(circle != land, "first and second initial slots rendered identically")
    for name in ("slot-one-draft", "saved-land", "reopened-land"):
        require(label(name) == land, f"{name}: slot 1 does not match the initial Land label in slot 2")
    for name in ("restore-draft", "restored-save", "reopened-circle"):
        require(label(name) == circle, f"{name}: slot 1 does not match its initial Circle label")
    log = (ROOT / "release.log").read_text(errors="replace")
    require("TotalReceived 1431 TotalReported 1431" in log, "incomplete GUI parameter download")
    require(log.count("Open MissionPlanner.GCSViews.ConfigurationView.ConfigFlightModes Flight Modes") >= 3,
            "page reopen records missing")
    provenance = json.loads((ROOT / "archive-comparison.json").read_text())
    require(provenance["release_files"] == provenance["matching"] == 1317 and
            not provenance["missing"] and not provenance["changed"], "release-file differences")
    require(provenance["archive_sha256"] == "ff3694f7a9038caf756545049dd7aef74e3d0d8fe3586e87aa881045704dd6f9",
            "unexpected input ZIP")
    writes = []
    armed = []
    pwm = set()
    for msg, sender, _, raw in frames(gzip.decompress((ROOT / "session.tlog.gz").read_bytes())):
        if msg == 0 and sender == (1, 1) and len(raw) >= 7:
            armed.append(bool(raw[6] & 128))
        if msg == 65 and sender == (1, 1) and len(raw) >= 14:
            pwm.add(int.from_bytes(raw[12:14], "little"))
        if msg == 23 and len(raw) >= 7:
            value, target, component, key, _ = struct.unpack("<fBB16sB", raw.ljust(23, b"\0"))
            writes.append((sender, target, component, key.split(b"\0")[0].decode("ascii"), value))
    require(armed and not any(armed), "primary link missing disarmed status or contains an armed heartbeat")
    require(pwm == {1800}, f"channel 5 PWM changed: {pwm}")
    require(writes == [((255, 190), 1, 1, "FLTMODE1", 9.0), ((255, 190), 1, 1, "FLTMODE1", 7.0)],
            f"unexpected primary-link parameter-write sequence: {writes}")
    print(f"primary link: {len(armed)} disarmed vehicle heartbeats; channel 5 PWM {pwm}; PARAM_SET {writes}")
    print("reopened labels matched; all 1,317 original release files matched the pinned ZIP")


if __name__ == "__main__":
    verify()
