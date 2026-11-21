"""Verify the original disconnected joystick page capture without launching Mission Planner."""
import hashlib
import json
from pathlib import Path
import re
import struct

HERE = Path(__file__).resolve().parent
ZIP = "ff3694f7a9038caf756545049dd7aef74e3d0d8fe3586e87aa881045704dd6f9"
SHOTS = {"setup": "cceafb835749ae3ad888740eeb05d91f5d61eba4357f24c070252c54b18b5b43",
         "optional": "6454aa87a3f970449527d2a474ef2bc0e59b99a41a7c867cb3e985776b032b11",
         "joystick": "be9286211bb3ce91bd83509674e634b362f6efa45b7dad79fbb5b639554c3066"}

def check(ok, label):
    if not ok:
        raise ValueError(label)

def verify():
    for name, digest in SHOTS.items():
        data = (HERE / (name + ".png")).read_bytes()
        check(hashlib.sha256(data).hexdigest() == digest and
              struct.unpack(">II", data[16:24]) == (1280, 800), name)
    check((HERE / "settled.png").read_bytes() == (HERE / "joystick.png").read_bytes(), "Second capture")
    comparison = json.loads((HERE / "archive-comparison.json").read_text())
    check(comparison["archive_sha256"] == ZIP and comparison["release_files"] == comparison["matching"] == 1317
          and not comparison["changed"] and not comparison["missing"], "Archive comparison")
    obs = (HERE / "observation.log").read_text()
    check(re.findall(r"^\s*(\w+):\s+\d+", obs, re.M) == ["lo"] and "Input device nodes: 0" in obs, "Guest")
    check(re.findall(r"^Clicked .+$", obs, re.M) == [
          "Clicked SETUP toolbar tab.", "Clicked Optional Hardware menu row.", "Clicked Joystick submenu row."],
          "Read-only actions")
    check('"      Joystick"' in (HERE / "optional.txt").read_text(), "Submenu")
    tree = (HERE / "settled.txt").read_text()
    check(re.findall(r'"RC (\d+)"', tree) == [str(n) for n in range(1, 17)], "RC rows")
    check(tree.count('"Detect"') == 10, "Default button rows")
    controls = ("Controller Axis", "Reverse", "Expo", "Output", "Enable", "Save", "Manual Control", "Elevons",
                "Loaded Config for ArduPlane")
    check(all(f'"{name}"' in tree for name in controls), "Joystick controls")
    trace = (HERE / "release-excerpt.log").read_text()
    check(all(key in trace for key in ("Open MissionPlanner.Joystick.JoystickSetup Joystick",
          "joystickbuttonsArduPlane.xml joystickaxisArduPlane.xml", "FileNotFoundException: /dev/input/by-id/",
          "JoystickLinux.getNumButtons", "getNumButtons 10")), "Joystick initialization")
    return {"original_release_files": 1317, "page": "MissionPlanner.Joystick.JoystickSetup",
            "device_nodes": 0, "disconnected_firmware_label": "ArduPlane", "rc_rows": 16,
            "fallback_button_rows": 10, "device_input_exercised": False}

if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
