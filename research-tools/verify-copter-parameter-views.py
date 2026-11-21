"""Replay the original Copter CONFIG session from its GUI captures and binary telemetry."""
from hashlib import sha256
import gzip
import json
from pathlib import Path
import runpy
import struct

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "gui-original-copter-sensors/sensors-cQ1U0M9J"
FIRST = RUN.with_name("sensors-f0A9eZw6")
SCREENS = {
    "config": "8a4de1b8c47a5b7751a0d7347fffd363e9daf20b302a16fb0e9d2cca2a041cc2",
    "list-open": "bda759d66c2ee30a8d102f3f9cd6a521ba0405076db016196e4502cf3eb75b86",
    "battery-filter": "5adb05ecc40f5cdbe7a92b9b6ed4352c8a020240ca1e3a8970bebc70df2e8134",
    "user-params": "76a664c1cf09c2f46a8a8e3b19631fe13ca9fb205519eac202c7a2225c741266",
    "fence-view": "66cc11c0506e62856bccd173b4a6df646566dbcb5df0ea41397eb0894aa01647",
}
CLASSES = ("ConfigSimplePids Basic Tuning", "ConfigRawParams Full Parameter List",
           "ConfigUserDefined User Params", "ConfigAC_Fence GeoFence")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def unpack_parameters(data):
    magic, count, total = struct.unpack_from("<HHH", data)
    require(magic == 0x671c and count == total, "expected a full export with defaults")
    formats = {1: "<b", 2: "<h", 3: "<i", 4: "<f"}
    result = {}
    previous = ""
    pos = 6
    while pos < len(data):
        if data[pos] == 0:
            pos += 1
            continue
        tag, lengths = struct.unpack_from("BB", data, pos)
        pos += 2
        fmt = formats[tag & 15]
        flags = tag >> 4
        size = struct.calcsize(fmt)
        prefix = lengths & 15
        suffix = 1 + (lengths >> 4)
        require(flags in (0, 1) and prefix <= len(previous), "unexpected packed record")
        name = previous[:prefix] + data[pos:pos + suffix].decode("ascii")
        pos += suffix
        value, = struct.unpack_from(fmt, data, pos)
        pos += size
        default = value
        if flags:
            default, = struct.unpack_from(fmt, data, pos)
            pos += size
        require(name not in result, "duplicate parameter: " + name)
        result[name] = (value, default)
        previous = name
    require(len(result) == count, "decoded count differs from header")
    return result


def replay_wire():
    reader = runpy.run_path(str(RUN.parent / "verify.py"))
    reader["CRC_EXTRA"][110] = 84  # FILE_TRANSFER_PROTOCOL in the same CRC-checked tlog reader
    logfile, = RUN.glob("*.tlog.gz")
    data = bytearray()
    requested = False
    session = estimated = end_offset = None
    chunks = beats = writes = 0
    for _, system, component, kind, payload in reader["packets"](gzip.decompress(logfile.read_bytes())):
        if kind == 0 and (system, component) == (1, 1):
            require(payload[4:6] == bytes((2, 3)) and not (payload[6] & 128), "unexpected vehicle state")
            beats += 1
        if kind == 23 and system == 255:
            writes += 1
        if kind != 110:
            continue
        packet = payload.ljust(254, b"\0")  # MAVLink 2 may trim trailing zero bytes
        _, sid, opcode, length, request, _, _, offset = struct.unpack_from("<HBBBBBBI", packet, 3)
        block = packet[15:15 + length]
        if (system, component) == (255, 190):
            if opcode == 4 and packet[1:3] == b"\x01\x01":
                require(not requested and block == b"@PARAM/param.pck?withdefaults=1", "unexpected file open")
                requested = True
            continue
        if (system, component) != (1, 1) or packet[1:3] != bytes((255, 190)):
            continue
        if (opcode, request) == (128, 4):
            require(requested and session is None, "unexpected open acknowledgement")
            estimated, = struct.unpack("<I", block)
            session = sid
        if request == 15:
            require(session == sid and offset == len(data) and end_offset is None,
                    "unexpected session, file offset or data after EOF")
            if opcode == 128:
                data.extend(block)
                chunks += 1
            else:
                require(opcode == 129 and block == b"\x06", "expected end of file")
                end_offset = offset
    require(end_offset == len(data) and beats > 0 and writes == 0, "incomplete transfer or unexpected write")
    values = unpack_parameters(data)
    expected = {"BATT2_MONITOR": (0, 0), "ACRO_BAL_ROLL": (1, 1), "ACRO_BAL_PITCH": (1, 1),
                "ACRO_RP_RATE": (360, 360), "ACRO_Y_RATE": (202.5, 202.5)}
    require(all(values.get(name) == pair for name, pair in expected.items()), "GUI value or default mismatch")
    require(values["RC7_OPTION"][0] == 7 and values["RC6_OPTION"][0] == 0, "user parameter mismatch")
    require(len(values) == 1431 and estimated == 12 * len(values), "unexpected file estimate or count")
    return {"parameters": len(values), "advertised_bytes": estimated, "actual_bytes": end_offset,
            "data_packets": chunks, "disarmed_heartbeats": beats, "parameter_writes": writes,
            "packed_sha256": sha256(data).hexdigest()}


def verify():
    for run in (FIRST, RUN):
        audit = json.loads((run / "archive-comparison.json").read_text())
        require(audit["release_files"] == audit["matching"] == 1317 and not audit["changed"]
                and not audit["missing"] and audit["archive_sha256"] ==
                "ff3694f7a9038caf756545049dd7aef74e3d0d8fe3586e87aa881045704dd6f9", "release identity")
    prefix = "Open MissionPlanner.GCSViews.ConfigurationView."
    log = (RUN / "release.log").read_text(errors="replace")
    require([x[len(prefix):] for x in log.splitlines() if x.startswith(prefix)] == list(CLASSES),
            "wrong sequence of page activations")
    require("TotalReceived 1431 TotalReported 1431" in log, "download incomplete")
    for name, digest in SCREENS.items():
        require(sha256((RUN / (name + ".png")).read_bytes()).hexdigest() == digest, "screenshot: " + name)
    warning = (RUN / "windows-list-ready.txt").read_text(encoding="utf-8")
    require("Raw Param Warning" in warning and "not min/max checked" in warning, "warning absent")
    failed = (FIRST / "windows-cancel-connection.txt").read_text(encoding="utf-8")
    require("Connecting Mavlink" in failed and prefix not in (FIRST / "release.log").read_text(errors="replace"),
            "first session boundary differs")
    wire = replay_wire()
    require((wire["actual_bytes"], wire["data_packets"], wire["disarmed_heartbeats"]) == (15968, 146, 600),
            "parameter archive or heartbeat counts differ from this session")
    require(wire["packed_sha256"] == "550deb92ff5d98750ac78274214ee7475e7dd651c6331ce0fc05a96d0f439733",
            "reconstructed parameter file differs from this session")
    return wire


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
