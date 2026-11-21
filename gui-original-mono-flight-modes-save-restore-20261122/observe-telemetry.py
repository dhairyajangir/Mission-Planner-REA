"""Generate only nominal read requests; decode vehicle telemetry offline."""
import argparse
import collections
import json
from pathlib import Path
from pymavlink.dialects.v20 import ardupilotmega as mav

parser = argparse.ArgumentParser()
parser.add_argument("operation", choices=["generate", "decode"])
parser.add_argument("file", type=Path)
args = parser.parse_args()
link = mav.MAVLink(None, srcSystem=254, srcComponent=190)
names = ["MAV_SYSID", "FRAME_CLASS", "FLTMODE_CH"] + [f"FLTMODE{n}" for n in range(1, 7)]
if args.operation == "generate":
    with args.file.open("wb") as stream:
        for name in names:
            payload = link.param_request_read_encode(1, 1, name.encode("ascii"), -1)
            stream.write(payload.pack(link))
            link.seq += 1
else:
    records = []
    counts = collections.Counter()
    with args.file.open("rb") as stream:
        while block := stream.read(16384):
            for message in link.parse_buffer(block) or []:
                kind = message.get_type()
                counts[kind] += 1
                if (message.get_srcSystem(), message.get_srcComponent()) != (1, 1):
                    continue
                if kind == "HEARTBEAT":
                    records.append({"kind": kind, "seq": message.get_seq(), "vehicle": message.type,
                                    "autopilot": message.autopilot, "base_mode": message.base_mode,
                                    "custom_mode": message.custom_mode, "armed": bool(message.base_mode & 128)})
                elif kind == "PARAM_VALUE" and message.param_id in names:
                    records.append({"kind": kind, "seq": message.get_seq(), "name": message.param_id,
                                    "value": message.param_value, "index": message.param_index,
                                    "count": message.param_count})
    print(json.dumps({"target": [1, 1], "message_counts": counts, "records": records}, indent=2))
