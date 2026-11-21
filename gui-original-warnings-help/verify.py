"""Verify evidence from Help and the independent Warning Manager form."""
import hashlib
import json
from pathlib import Path
import re
import struct

HERE = Path(__file__).resolve().parent
ZIP = "ff3694f7a9038caf756545049dd7aef74e3d0d8fe3586e87aa881045704dd6f9"

def check(condition, message):
    if not condition:
        raise ValueError(message)

def verify():
    shots = json.loads((HERE / "screenshots.json").read_text())
    check(set(shots) == {"help-page", "tools-ready", "manager-open", "manager-repaint"}, "Screenshot set")
    for label, checksum in shots.items():
        png = (HERE / (label + ".png")).read_bytes()
        check(png[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", png[16:24]) == (1280, 800), label)
        check(hashlib.sha256(png).hexdigest() == checksum, label)
    archive = json.loads((HERE / "archive-comparison.json").read_text())
    check(archive["archive_sha256"] == ZIP and archive["matching"] == archive["release_files"] == 1317
          and not (archive["missing"] or archive["changed"]), "Release file comparison")
    observation = (HERE / "observation.log").read_text()
    check(re.findall(r"^\s*(\w+):\s+\d+", observation, re.M) == ["lo"], "Network interfaces")
    actions = re.findall(r"^\S+Z \d+ (\w+) \d+ \d+ ([\w-]+)$", observation, re.M)
    check(actions == [("click", "help-page"), ("ctrlf", "tools-opening"), ("waittools", "tools-ready"),
                      ("showmanager", "manager-open"), ("redrawmanager", "manager-repaint"),
                      ("done", "finish")], "Actions")
    application = (HERE / "release-excerpt.log").read_text()
    check("Open MissionPlanner.GCSViews.Help Help" in application and
          "Open MissionPlanner.temp .ctor" in application and "SerialOutputMD" not in application, "Application route")
    help_controls = (HERE / "help-controls.txt").read_text()
    check(all(f'"{c}"' in help_controls for c in ["Check for Updates", "Check for BETA Updates",
          "Change Log", "Show Console Window (restart)"]), "Help controls")
    tools = (HERE / "tools-ready.txt").read_text()
    check('"Warning Manager"' in tools and '"Create custom audio warnings"' in tools, "Tools entry")
    manager = (HERE / "manager-tree.txt").read_text().splitlines()
    check(re.match(r'^     0x[\da-f]+ "Warning Manager":', manager[0]), "Top-level dialog")
    controls = re.findall(r'^           0x[\da-f]+ "([^"]+)":', "\n".join(manager), re.M)
    check(set(controls) == {"Color", "Item type", "Message", "Repeat Interval", "Trigger",
                            "Comparison", "Field", "Save", "+"}, "Warning Manager controls")
    return {"original_release_files": 1317, "main_screen": "MissionPlanner.GCSViews.Help",
            "separate_window": "Warning Manager", "named_dialog_controls": len(controls),
            "warning_rule_exercised": False, "screenshots": len(shots)}

if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
