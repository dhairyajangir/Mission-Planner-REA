"""Verify the retained original GeoRef window and its mode change without a running GUI."""
import hashlib
import json
from pathlib import Path
import re
from PIL import Image

RUN = Path(__file__).resolve().parent / "capture"
PNG = {
    "startup":"6d5dde2619bd843cf990241480febc9d0b429b39d2a4e690960d82c84e611579",
    "tools":"6a929f69ce26224331d68439c0d389d315a0c6535abe8d1f5bd10ee6990a996a",
    "georef":"9a72a4e1ecc3928fecb02b49bd0c08bccc6579220738491bd6aa04147dc37a0a",
    "georef-visible":"0e983dd06d53f7ff7e1a4d96bfe827f9df97a581e690b2e063bff180c0e7efb3",
    "offset":"cdf000b78cd60e2b99573ba8f675dfed055d86bb53a5521137dc7ffaae38b019",
}

def require(value, message):
    if not value:
        raise ValueError(message)

def verify():
    audit = json.loads((RUN/"archive-comparison.json").read_text())
    require(audit["release_files"] == audit["matching"] == 1317 and audit["changed"] == audit["missing"] == []
            and len(audit["added"]) == 2 and all(n.endswith("MissionPlanner.log") for n in audit["added"])
            and audit["archive_sha256"] == "ff3694f7a9038caf756545049dd7aef74e3d0d8fe3586e87aa881045704dd6f9", "release comparison")
    log = (RUN/"release.log").read_text(errors="replace")
    require([s for s in log.splitlines() if s.startswith("Open MissionPlanner.")] == [
        "Open MissionPlanner.GCSViews.FlightData FlightData","Open MissionPlanner.GCSViews.Help Help",
        "Open MissionPlanner.temp .ctor","Open MissionPlanner.GeoRef.Georefimage Geo Ref Images"], "original release page order")
    actions = (RUN/"observation.log").read_text()
    for s in ("a49e30e2cd635836cd737f112f419da2d3c46c59716ee08122e2986013b79f2a  MissionPlanner.exe",
              "20:50:45Z Click Geo ref images in tools","20:50:55Z Select Time offset", "Finished with inputs empty"):
        require(s in actions,s)
    for label, digest in PNG.items():
        require(hashlib.sha256((RUN/(label+".png")).read_bytes()).hexdigest() == digest,label)
    controls = ("Browse Log","Browse Pictures","Time offset","CAM Message","Trigger Message","Estimate Offset",
                "Seconds offset","Use AMSL Alt","Use GPS2","Pre-process","Location Kml","GeoTag Images")
    for label in ("georef-visible","offset"):
        tree = (RUN/(label+"-tree.txt")).read_text()
        subtree = re.search(r'(?ms)^     0x[0-9a-f]+ "Geo Ref Images":.*?(?=^     0x[0-9a-f]+ |\Z)',tree).group()
        require("1180x730+8+8" in subtree and all('"'+s+'"' in subtree for s in controls), "dialog subtree")
    white,black,disabled = (255,255,255),(0,0,0),(236,233,216)
    for label,colors in (("georef-visible",[white,black,disabled,white]),("offset",[black,white,white,disabled])):
        with Image.open(RUN/(label+".png")) as im:
            rgb = im.convert("RGB")
            # Radio centres, then blank interiors of seconds-offset and shutter-lag text boxes.
            require([rgb.getpixel(p) for p in ((101,106),(275,106),(210,163),(570,163))] == colors,
                    "rendered selection and enabled fields for " + label)
    return {"release_files":1317,"screenshots":len(PNG),"visible_controls":len(controls),"initial":"CAM Message","selected":"Time offset"}

if __name__ == "__main__":
    print(verify())
