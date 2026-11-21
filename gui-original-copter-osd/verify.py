"""Replay retained page selection, platform gate, release identity and vehicle telemetry."""
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import runpy
import struct

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
RUN = HERE / "manual-verified"

def need(test, label):
    if not test: raise ValueError(label)

def collect():
    raw = gzip.decompress((RUN/"vehicle.tlog.gz").read_bytes())
    decode = runpy.run_path(str(REPO/"gui-original-copter-sensors/verify.py"))["packets"]
    heartbeats, writes = [], []
    for stamp,sysid,compid,kind,payload in decode(raw):
        if (sysid,compid,kind) == (1,1,0):
            need(payload[4:6] == bytes([2,3]) and not payload[6] & 128,"Copter state")
            heartbeats.append(stamp/1e6)
        if sysid == 255 and kind == 23:
            writes.append([payload[6:22].rstrip(b"\0").decode(),struct.unpack_from("<f",payload)[0]])
    actions = (RUN/"observation.log").read_text()
    brackets = {}
    for label in ("hardware-osd","config"):
        found = re.search(r"(?m)^(\S+Z) click \d+ \d+ "+label+r"$",actions)
        click = datetime.fromisoformat(found.group(1).replace("Z","+00:00")).timestamp()
        duration = 8 if label == "hardware-osd" else 6
        before = max(t for t in heartbeats if t<=click)
        after = min(t for t in heartbeats if t>=click+duration)
        need(click-before < 3 and after-click-duration < 3,"heartbeat bracket")
        brackets[label] = [datetime.fromtimestamp(x,timezone.utc).isoformat() for x in (click,before,after)]
    log = (RUN/"release.log").read_text(errors="replace")
    need("Open MissionPlanner.GCSViews.ConfigurationView.ConfigHWOSD OSD" in log,"hardware page activation")
    need("Open MissionPlanner.GCSViews.ConfigurationView.ConfigOSD " not in log,"unexpected onboard editor activation")
    need("Open MissionPlanner.GCSViews.SoftwareConfig" in log and "TotalReceived 1431 TotalReported 1431" in log,"connected CONFIG page")
    tree = (RUN/"hardware-osd-tree.txt").read_text()
    need("ArduCopter V4.8.0-dev" in tree and '"Enable Telemetry"' in tree,"OSD button in control tree")
    need('You only need to use this if you are having issue with your OSD not updating' in tree,"OSD explanation")
    il = (HERE/"registration.txt").read_text()
    need("ConfigHWOSD" in il and "MissionPlanner.Program::MONO\nIL_01f4: brtrue.s IL_0221" in il and
         il.index("ConfigOSD::IsApplicable") < il.index("ldtoken MissionPlanner.GCSViews.ConfigurationView.ConfigOSD"),"release registration")
    audit = json.loads((RUN/"archive-comparison.json").read_text())
    need(audit["release_files"] == audit["matching"] == 1317 and not audit["changed"] and not audit["missing"],"postrun archive equality")
    need(audit["archive_sha256"] == "ff3694f7a9038caf756545049dd7aef74e3d0d8fe3586e87aa881045704dd6f9","release archive")
    pictures = {f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(RUN.glob("*.png"))}
    return {"screenshots":pictures,"disarmed_heartbeats":len(heartbeats),"page_brackets":brackets,
            "outbound_param_set":writes,"tlog_sha256":hashlib.sha256(raw).hexdigest(),"release_files":audit["matching"]}

def verify():
    result = collect()
    need(result == json.loads((HERE/"verification.json").read_text()),"retained manifest differs")
    return result

if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--record"]:
        (HERE/"verification.json").write_text(json.dumps(collect(),indent=2)+"\n",encoding="utf-8")
    print(verify())
