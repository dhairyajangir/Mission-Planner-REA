"""Verify the original manager window and its release assembly and profile evidence offline."""
import hashlib
import json
from pathlib import Path
import re
import struct
from xml.etree import ElementTree

HERE = Path(__file__).resolve().parent
ZIP = "ff3694f7a9038caf756545049dd7aef74e3d0d8fe3586e87aa881045704dd6f9"
EXE = "a49e30e2cd635836cd737f112f419da2d3c46c59716ee08122e2986013b79f2a"
SHOTS = {"startup": "6d5dde2619bd843cf990241480febc9d0b429b39d2a4e690960d82c84e611579",
         "manager-open": "3385e7a6b1543ec375dd6d6ce4ade9530c2c9300f6fb275023d23a4c0559f0b7",
         "manager-settled": "3385e7a6b1543ec375dd6d6ce4ade9530c2c9300f6fb275023d23a4c0559f0b7"}

def check(ok, subject):
    if not ok:
        raise ValueError(subject)

def verify():
    for label, digest in SHOTS.items():
        data = (HERE / (label + ".png")).read_bytes()
        check(hashlib.sha256(data).hexdigest() == digest and struct.unpack(">II", data[16:24]) == (1280, 800), label)
    archive = json.loads((HERE / "archive-comparison.json").read_text())
    check(archive["archive_sha256"] == ZIP and archive["matching"] == archive["release_files"] == 1317
          and not archive["missing"] and not archive["changed"], "Archive comparison")
    types = json.loads((HERE / "release-types.json").read_text(encoding="utf-8-sig"))
    check(types["member_sha256"] == EXE and types["assembly"] == "MissionPlanner"
          and types["mvid"] == "b0e70e19-ad56-4dc7-bb0b-8e33a4ca21c0", "Release assembly")
    methods = types["type_methods"]
    check(set(methods) == {"MissionPlanner.Controls.PluginUI", "MissionPlanner.Plugin.Plugin",
                           "MissionPlanner.Plugin.PluginLoader"}, "Owner types")
    check({"PopulateGridView", "bSave_Click", "UpdateDisabledPlugins"}.issubset(methods["MissionPlanner.Controls.PluginUI"]),
          "Manager type methods")
    tree = (HERE / "manager-tree.txt").read_text()
    check(all(f'"{n}"' in tree for n in ("PluginManager", "Show Errors", "Save && Close")), "Original window")
    obs = (HERE / "observation.log").read_text()
    check(re.findall(r"^\s*(\w+):\s+\d+", obs, re.M) == ["lo"] and EXE in obs
          and "Pressed Ctrl+P" in obs and "no input to the PluginManager window" in obs, "Offline route")
    profile = (HERE / "initial-user-config.xml").read_bytes()
    baseline = HERE.parent / "gui-original-mono-evidence-20261122/disconnected/initial-user-config.xml"
    expected = ElementTree.fromstring(profile).findtext("DisabledPlugins").split(";")
    check(baseline.read_bytes().replace(b"\r\n", b"\n") == profile.replace(b"\r\n", b"\n")
          and len(expected) == len(set(expected)) == 55, "Established plugin fixture")
    settings = json.loads((HERE / "settings-comparison.json").read_text())
    check(settings["before"]["disabled_plugins"] == settings["after"]["disabled_plugins"] == expected, "Plugin selections")
    lines = (HERE / "release-excerpt.log").read_text().splitlines()
    check([l.split("Plugin Init ")[1] for l in lines if "Plugin Init " in l] ==
          ["Grid 1.3.9384.38250 by Michael Oborne"], "Built-in Grid instance")
    check(any("Plugin example2.cs is disabled in config.xml" in l for l in lines), "Example file")
    return {"manager": "MissionPlanner.Controls.PluginUI", "source_module": "Plugin",
            "builtin_grid": True, "disabled_profile_entries": len(expected),
            "external_plugin_interaction": False, "original_release_files": 1317}

if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
