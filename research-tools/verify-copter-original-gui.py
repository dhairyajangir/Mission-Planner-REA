"""Check the retained core Copter GUI, waypoint roundtrip and release IL evidence offline."""
from collections import Counter
from contextlib import closing
import hashlib
import json
import runpy
import sqlite3
import struct


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


SCREENS = {
    "startup": ("56078e146500cb4c2ea1aaf9b0631596e36f4145e3549e4cc1fde370460af022", ('"Quick"',)),
    "setup": ("569fd0e9f3dfeda7ccbb10455e3a8e77d34752c9a4ee354446aa2ca71309d49b", ('">> Mandatory Hardware"',)),
    "mandatory": ("09673dd32868978c238ea1fc93699a4dabf2aecca3f786e5f91a36d8fd2e8735",
                  ("The following pages are required", "Accel Calibration", "Radio Calibration")),
    "frame-type": ("ad685d6e3f8bdb139c26002c8772569c01b831ab7db6f6e29f12ad83e8ea335c",
                   ('"Frame Class"', '"Quad"', '"Frame Type"')),
    "flight-modes": ("c830f75220ed5ee46223e914cbbf9a96a4d23f0ae7065563f902ed6c24f33aa1",
                     ('"5: 1800"', '"Stabilize"', '"Save Modes"', '"PWM 1750 +"')),
    "failsafe": ("41c0dd33c9d8285edc495b31870431628b851c58ee580462f111fd86c54ab11b",
                 ('"Ensure your props are not on the Plane/Quad"', '"Dissarmed"', '"FS Pwm"')),
}

PLAN_SCREENS = {
    "plan": "354a6de6d82689bac0b1ead5c2bf1ab31461d78616bb75b1801b174a251a6285",
    "load-dialog": "8a98a73504f5cf7c5ff42871ac5770ecc755b0f9cda0dd4e67d19e150626368e",
    "load-result": "3f7a12d79f70066a24672a51fabc62f38330091926243e216c9eb98a87b8a185",
    "accepted-home": "1eb394eff44e94c5a9aa4cc8f649023e58a31bfaa18643c1ca12fa08b215f6b7",
    "roundtrip/save-result": "1395cc77c49ffeb56068ea155a82ddcc97604e69538dac2bbfbc98b4f6919a4b",
}


SENSOR_PAGES = (
    ("mandatory", "ConfigMandatory Mandatory Hardware", "09673dd32868978c238ea1fc93699a4dabf2aecca3f786e5f91a36d8fd2e8735"),
    ("accel", "ConfigAccelerometerCalibration Accel Calibration", "17c5c9985d37dcf189e796ac14ce1e8f356b98e6aae7827625a888f611c647ae"),
    ("compass", "ConfigHWCompass2 Compass", "1a1e2d725dde6d8ee4e42a90f5837771a4a3fc010e0933bbf9235c4fef299ea0"),
    ("radio-input", "ConfigRadioInput Radio Calibration", "c19ad2add32af000cb65a90416a62f52c70168f3c212062ffdc3d2aa6b7426b4"),
    ("servo-output", "ConfigRadioOutput Servo Output", "b43aefda931d8808447516a3149b0408f2afb8c5dd48933913099f7cd775719d"),
    ("hardware-id", "ConfigHWIDs HW ID", "7bb2ab059256542c09c7c315cfa2665120c385253435b578a1d34924d7865817"),
    ("optional", "ConfigOptional Optional Hardware", "948c89ac4a1f06865539083eedca39fe8e187442d3d14a1cd6b0c198f8024e9a"),
    ("battery", "ConfigBatteryMonitoring Battery Monitor", "734eb7a55ce9efbad997d9e02558ecea06cb4b9cf88b6f1cb2e93785a4116755"),
    ("battery-two", "ConfigBatteryMonitoring2 Battery Monitor 2", "03d96ae28ca52eeed0d87d1107e7d321a28f54645694f02d17e1641b2f95880e"),
)


def supplemental_pages(folder):
    prefix = "Open MissionPlanner.GCSViews.ConfigurationView."
    opened = [line[len(prefix):] for line in (folder / "release.log").read_text(errors="replace").splitlines()
              if line.startswith(prefix)]
    labels = [line.rsplit(" label ", 1)[1] for line in (folder / "observation.log").read_text().splitlines()
              if " label " in line]
    return (opened == [page for _, page, _ in SENSOR_PAGES] and
            labels == ["setup", "mandatory", "accel", "compass", "radio-input", "servo-output", "hardware-id",
                       "optional", "optional-scroll", "battery", "battery-scroll", "battery-two", "final-hud"] and
            all(digest(folder / (name + ".png")) == expected for name, _, expected in SENSOR_PAGES))


def serial_readback(folder):
    raw = (folder / "serial1-1.bin").read_bytes()
    expected = json.loads((folder / "serial1-1.json").read_text())
    names = {0: "HEARTBEAT", 1: "SYS_STATUS", 22: "PARAM_VALUE", 49: "GPS_GLOBAL_ORIGIN",
             111: "TIMESYNC", 242: "HOME_POSITION"}
    counts = Counter()
    mode_values = {"MAV_SYSID": 1, "FRAME_CLASS": 1, "FLTMODE_CH": 5,
                   **{f"FLTMODE{i}": value for i, value in enumerate((7, 9, 6, 3, 5, 0), 1)}}
    records, seen_params = [], Counter()
    offset = 0
    while offset < len(raw):
        header = raw[offset:offset + 10]
        if len(header) != 10 or header[0] != 253 or header[2] != 0:
            return False
        payload = raw[offset + 10:offset + 10 + header[1]]
        offset += 12 + header[1]  # 10-byte MAVLink 2 header plus checksum
        if offset > len(raw) or len(payload) != header[1]:
            return False
        message = names.get(int.from_bytes(header[7:10], "little"))
        counts[message] += 1
        if header[5:7] != bytes((1, 1)):
            continue
        if message == "HEARTBEAT":
            mode, vehicle, autopilot, base_mode, _, _ = struct.unpack("<IBBBBB", payload)
            if (mode, vehicle, autopilot, base_mode) != (0, 2, 3, 81):
                return False
            records.append(dict(kind=message, seq=header[4], vehicle=vehicle, autopilot=autopilot,
                                base_mode=base_mode, custom_mode=mode, armed=bool(base_mode & 128)))
        elif message == "PARAM_VALUE":
            value, count, index, name, _ = struct.unpack("<fHH16sB", payload)
            name = name.rstrip(b"\0").decode("ascii")
            if name == "STAT_RUNTIME":  # This incidental parameter is outside the observer's requested set.
                continue
            if mode_values.get(name) != value or count != 1431 or index != 65535:
                return False
            seen_params[name] += 1
            records.append(dict(kind=message, seq=header[4], name=name, value=value, count=count, index=index))
    return (hashlib.sha256(raw).hexdigest() == "0740b319f65f33202811a00f5b2c71fed002a03d1279ab7ddb1f4517e98e2788"
            and expected["target"] == [1, 1] and counts == expected["message_counts"]
            and records == expected["records"] and seen_params == {key: 2 for key in mode_values}
            and sum(row["kind"] == "HEARTBEAT" for row in records) == 14)


def compiled_il(root):
    binary = root / "mission-planner-binary-evidence"
    il = binary / "copter-flight-mode-display-il.txt"
    page = "MissionPlanner.GCSViews.ConfigurationView.ConfigFlightModes"
    with closing(sqlite3.connect((binary / "rea-main-index.sqlite").resolve().as_uri() + "?mode=ro", uri=True)) as db:
        methods = db.execute("select token, name, il_sha256, body_status from methods where declaring_type=? "
                             "and name in ('timer_Tick','readSwitch') order by token", (page,)).fetchall()
        edge = db.execute("select target_token, target_name from calls where caller_token=? and il_offset=?",
                          ("0x06000f3d", 816)).fetchall()
    return (digest(il) == "5c5f179397635e9137a01c1e05a25d9327f12899b230ce9845da71131ac801cc"
            and methods == [
                ("0x06000f3d", "timer_Tick", "c5de19f3c2a674b31c0837735a031879412fb55b2309b41b896ce496ad558492", "present"),
                ("0x06000f3e", "readSwitch", "0fd4200edc4ff4a63f68d2f5fbbf82fee60c4617db54e192ab7b55b04671b792", "present")]
            and edge == [("0x06000f3e", "readSwitch")]
            and "IL_0330: call System.Byte " + page + "::readSwitch(System.Single)" in il.read_text())


def verify(root, check):
    folder = root / "gui-original-mono-evidence-20261122/connected"
    obs = (folder / "observation.log").read_text(errors="replace")
    archive = json.loads((folder / "archive-comparison.json").read_text())
    check("connected original Mono release and simulator provenance",
          archive["matching"] == archive["release_files"] == 1317 and archive["missing"] == archive["changed"] == []
          and archive["archive_sha256"] == digest(root / "mission-planner-portable.zip")
          and "Mono JIT compiler version 6.8.0.105" in obs
          and "24afb2e186bcdf66c66d7cb5b88fb7afeaa2a0b89bf63c9d58e4fb2029ac2b54  /sim/arducopter" in obs
          and "Connection on serial port 5760" in (folder / "copter.log").read_text(),
          "One isolated release and disposable Copter under Mono; startup plugins disabled.")
    for name, (image_hash, cues) in SCREENS.items():
        tree = (folder / ("windows-" + name + ".txt")).read_text(encoding="utf-8")
        check("original Mono GUI Copter " + name, digest(folder / (name + ".png")) == image_hash
              and "ArduCopter V4.8.0-dev (15a10bb4)" in tree and "TCP5760-1-QUADROTOR" in tree
              and all(cue in tree for cue in cues),
              "Reviewed release-window PNG and X11 control tree from the disarmed core observation.")
    check("Copter core disarmed SERIAL1 observations", serial_readback(folder),
          "Raw bounded capture decoded separately from the saved observer summary; no airborne inference.")
    plan = root / "gui-original-plan-evidence"
    try:
        runpy.run_path(str(root / "research-tools/verify-original-plan-roundtrip.py"))["main"]()
        wpl_ok = True
    except (OSError, ValueError) as error:
        print(error)
        wpl_ok = False
    check("original Mono PLAN local import and save",
          wpl_ok and all(digest(plan / (stem + ".png")) == value for stem, value in PLAN_SCREENS.items()),
          "Two disconnected guests, local home and two waypoints, 36 fields; command catalogue reported Plane.")
    check("ConfigFlightModes compiled method bodies and call edge", compiled_il(root),
          "Release IL listing tied to indexed method hashes and the timer callback's readSwitch call.")
    sensor_root = root / "gui-original-copter-sensors"
    sensor_folder = sensor_root / "sensors-FjBlM50a"
    check("nine supplemental original Mono Copter setup pages", supplemental_pages(sensor_folder),
          "Each reviewed PNG is paired with the exact ordered release page activation and navigation event.")
    replay = runpy.run_path(str(sensor_root / "verify.py"))["collect"]()
    reported = json.loads((sensor_folder / "verification.json").read_text())
    value = 10.100000381469727
    check("supplemental GUI telemetry and battery-page parameter write",
          replay == reported and replay["archive_matching_files"] == 1317
          and (replay["vehicle_heartbeats"], replay["armed_heartbeats"]) == (518, 0)
          and set(replay["captures"]) == {name for name, _, _ in SENSOR_PAGES}
          and replay["gcs_param_set"] == [{"utc": "2026-11-21T19:13:04.237737+00:00",
                                           "name": "BATT_VOLT_MULT", "value": value}]
          and replay["gcs_preflight_storage"] == [{"utc": "2026-11-21T19:13:14.422378+00:00", "param1": 1.0}]
          and [sample["value"] for sample in replay["vehicle_batt_volt_mult_param_value"]] == [value, value]
          and "setParam gotback BATT_VOLT_MULT : 10.1" in (sensor_folder / "release.log").read_text(errors="replace"),
          "Disarmed samples bracket every page. After battery navigation the GCS sent the existing multiplier "
          "and later a preflight storage command; the returned multiplier matched.")
