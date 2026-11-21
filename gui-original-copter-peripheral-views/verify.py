"""Replay retained window evidence and vehicle traffic using the Python standard library."""
import argparse
import collections
import gzip
import hashlib
import json
from datetime import datetime
from pathlib import Path
import re
import runpy

ROOT = Path(__file__).resolve().parent
TOOLS = runpy.run_path(str(ROOT.parent / "gui-original-copter-sensors/verify.py"))
PAGES = {"serial": "ConfigSerial", "can-gps-order": "ConfigGPSOrder", "rtk": "ConfigSerialInjectGPS"}
# MAVLink common.xml CRC extras for audited messages. The shared parser checks checksums,
# including all vehicle heartbeats, all decoded GCS commands and all selected write types.
MESSAGES = {0: ("HEARTBEAT", 50), 20: ("PARAM_REQUEST_READ", 214),
            21: ("PARAM_REQUEST_LIST", 159), 22: ("PARAM_VALUE", 220),
            23: ("PARAM_SET", 168), 66: ("REQUEST_DATA_STREAM", 148),
            75: ("COMMAND_INT", 158), 76: ("COMMAND_LONG", 152), 110: ("FILE_TRANSFER_PROTOCOL", 84),
            123: ("GPS_INJECT_DATA", 250), 126: ("SERIAL_CONTROL", 220),
            233: ("GPS_RTCM_DATA", 35), 323: ("PARAM_EXT_SET", 78)}
TOOLS["CRC_EXTRA"].update({k: spec[1] for k, spec in MESSAGES.items()})

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def outbound_frames(data):
    """Count every recorded GCS message ID, including IDs outside the decoded set."""
    index = 0
    while index < len(data):
        start = index + 8
        timestamp = int.from_bytes(data[index:start], "big") / 1_000_000
        magic, size = data[start:start + 2]
        if magic == 253:
            sid = data[start + 5]
            kind = int.from_bytes(data[start + 7:start + 10], "little")
            index = start + 12 + size + (13 if data[start + 2] & 1 else 0)
        elif magic == 254:
            sid, _, kind = data[start + 3:start + 6]
            index = start + 8 + size
        else:
            raise ValueError("Unexpected packet framing")
        if index > len(data):
            raise ValueError("Incomplete packet")
        if sid == 255:
            yield timestamp, kind

def inspect(run):
    log = (run / "release.log").read_text(errors="replace")
    observation = (run / "observation.log").read_text()
    copter = (run / "copter.log").read_text()
    archive = json.loads((run / "archive-comparison.json").read_text())
    if archive["matching"] != archive["release_files"] or archive["changed"] or archive["missing"]:
        raise ValueError("Release archive comparison failed")
    telemetry = run / "vehicle.tlog.gz"
    result = {"matching_release_files": archive["matching"], "archive_sha256": archive["archive_sha256"],
              "startup_complete_log": "appload time" in log,
              "sitl_waited_for_tcp": "Waiting for connection" in copter,
              "telemetry_retained": telemetry.is_file(), "pages": {}}
    result["startup_evidence_sha256"] = {name: digest(run / name) for name in
                                         ("startup.png", "windows-startup.txt", "release.log", "observation.log", "copter.log")}
    result["application_logged_tcp_open"] = "TCP Open 127.0.0.1 5760" in log
    result["application_logged_autoconnect_start"] = "start AutoConnect" in log
    if "Full thread dump:" in log:
        base_thread = next(block for block in log.split("Full thread dump:")[-1].split("\n\n")
                           if block.startswith('"Base Thread"'))
        result["sampled_ui_stack"] = [s for s in ("JsonSerializerInternalReader.CreateList", "Extensions.FromJSON",
                                                 "AutoConnect.Start", "MainV2.OnLoad") if s in base_thread]
    actions = {label: datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
               for ts, label in re.findall(r"(?m)^(\S+Z): click \([^)]*\) label (\S+)$", observation)}
    if telemetry.is_file():
        stamps, armed, tx, commands, ftp = [], 0, [], [], []
        data = gzip.decompress(telemetry.read_bytes())
        outbound = list(outbound_frames(data))
        for us, sid, cid, kind, body in TOOLS["packets"](data):
            if kind == 0 and (sid, cid) == (1, 1):
                assert body[4:6] == bytes([2, 3]), "Unexpected vehicle type"
                stamps.append(us / 1_000_000)
                armed += bool(body[6] & 128)
            if sid == 255:
                tx.append((us / 1_000_000, MESSAGES[kind][0]))
                if kind in (75, 76):
                    commands.append((us / 1_000_000, int.from_bytes(body[28:30], "little")))
                elif kind == 110:
                    header = body[3:].ljust(12, b"\0")
                    opcode = header[3]
                    path = header[12:12 + header[4]].rstrip(b"\0").decode("ascii") if opcode == 4 else None
                    ftp.append((us / 1_000_000, opcode, path))
        result.update(heartbeats=len(stamps), armed_heartbeats=armed, tlog_gz_sha256=digest(telemetry),
                      all_gcs_ids=dict(sorted(collections.Counter(str(k) for _, k in outbound).items())),
                      selected_gcs_messages=dict(sorted(collections.Counter(name for _, name in tx).items())),
                      gcs_commands=dict(sorted(collections.Counter(str(c) for _, c in commands).items())))
    for label, klass in PAGES.items():
        if label not in actions:
            continue
        stamp = actions[label]
        tree = run / f"windows-{label}.txt"
        assert telemetry.is_file() and stamps and not armed, "Missing disarmed vehicle evidence"
        assert "ArduCopter V4.8.0-dev" in tree.read_text(), "Connected title missing"
        assert re.search(r"(?m)^Open MissionPlanner.GCSViews.ConfigurationView\." + klass + r"\s", log), klass
        assert any(stamp - 3 <= h <= stamp for h in stamps) and any(stamp + 5 <= h <= stamp + 8 for h in stamps)
        result["pages"][label] = {
            "image_sha256": digest(run / (label + ".png")), "tree_sha256": digest(tree),
            "ftp_first_6s": [{"opcode": op, "open_read_only_path": path}
                             for t, op, path in ftp if stamp <= t < stamp + 6],
            "all_gcs_ids_first_6s": dict(sorted(collections.Counter(
                str(k) for t, k in outbound if stamp <= t < stamp + 6).items())),
            "selected_gcs_messages_first_6s": dict(sorted(collections.Counter(
                name for t, name in tx if stamp <= t < stamp + 6).items())),
            "gcs_commands_first_6s": dict(sorted(collections.Counter(
                str(c) for t, c in commands if stamp <= t < stamp + 6).items()))}
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    attempts = sorted(path for path in (ROOT / "startup-attempts").glob("*") if path.is_dir())
    if (ROOT / "archive-comparison.json").exists():
        attempts.append(ROOT)
    if not attempts:
        raise SystemExit("No finalized observation")
    computed = {("connected" if path == ROOT else path.name): inspect(path) for path in attempts}
    target = ROOT / "verification.json"
    if args.check:
        if json.loads(target.read_text()) != computed:
            raise SystemExit("Evidence differs from retained verification")
    else:
        target.write_text(json.dumps(computed, indent=2) + "\n", encoding="utf-8")
    print({run: list(record["pages"]) for run, record in computed.items()})

if __name__ == "__main__":
    main()
