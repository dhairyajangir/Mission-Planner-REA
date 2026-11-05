"""Verify typed fence replacement after one legacy write in disposable SITL."""
import hashlib
import json
import math
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
out = root/'sitl-evidence/command-ack-fence_advanced_write'
sys.path.insert(0,str(root/'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
relay = json.loads((out/'relay-result.json').read_text())
assert relay['case'] == 'fence_advanced_write' and not relay['errors'] and relay['closed_by'] == 'client'
assert relay['buffered_bytes_at_close'] == 0 and relay['binary_sha256'] == sha(root/'sitl-evidence/arducopter')
assert all(sha(out/name) == digest for name,digest in relay['capture_sha256'].items())
def decode(path):
    parser = ardupilotmega.MAVLink(None); parser.robust_parsing = True
    found,bad = [],0
    for byte in path.read_bytes():
        msg = parser.parse_char(bytes([byte]))
        if msg is None: continue
        if msg.get_type() == 'BAD_DATA': bad += 1; continue
        d = msg.to_dict(); d['source'] = [msg.get_srcSystem(),msg.get_srcComponent()]; found.append(d)
    return found,bad
up,bad_up = decode(out/'to_sitl_output.bin'); down,bad_down = decode(out/'to_client_output.bin')
pick = lambda rows,kind: [m for m in rows if m['mavpackettype'] == kind]
uploads = [m for m in pick(up,'MISSION_ITEM_INT') if m['mission_type'] == 1]
acks = [m for m in pick(down,'MISSION_ACK') if m['mission_type'] == 1 and m['source'] == [1,1]]
writes = pick(up,'FENCE_POINT'); fetches = pick(up,'FENCE_FETCH_POINT')
responses = [m for m in pick(down,'FENCE_POINT') if m['source'] == [1,1]]
counts = [m for m in pick(down,'MISSION_COUNT') if m['mission_type'] == 1 and m['source'] == [1,1]]
readback = [m for m in pick(down,'MISSION_ITEM_INT') if m['mission_type'] == 1 and m['source'] == [1,1]]
heartbeats = [m for m in pick(down,'HEARTBEAT') if m['source'] == [1,1]]
assert [m['seq'] for m in uploads] == list(range(5)) and [m['command'] for m in uploads] == [5000,5001,5001,5001,5004]
assert [m['param1'] for m in uploads] == [0,3,3,3,25] and any(m['type'] == 0 for m in acks)
assert len(writes) == len(fetches) == len(responses) == 1 and writes[0]['idx'] == 0 and writes[0]['count'] == 6 and fetches[0]['idx'] == 0
assert len(counts) == 1 and counts[0]['count'] == 1 and len(readback) == 1 and readback[0]['seq'] == 0 and readback[0]['command'] == 5000
def distance(a,b,c,d):
    v=math.sin(math.radians(c-a)/2)**2+math.cos(math.radians(a))*math.cos(math.radians(c))*math.sin(math.radians(d-b)/2)**2
    return 2*6371000*math.asin(math.sqrt(v))
assert distance(readback[0]['x']/1e7,readback[0]['y']/1e7,-35.3635,149.1655) < 5
assert distance(writes[0]['lat'],writes[0]['lng'],-35.3635,149.1655) < 5
assert heartbeats and all(not(m['base_mode'] & 128) for m in heartbeats)
assert (out/'probe-exit.txt').read_text().strip() == '0'
log = (out/'probe.log').read_text(encoding='utf8',errors='replace')
assert all(s in log for s in ['LEGACY_TOTAL=6','LEGACY_WRITE_RESULT=True','TYPED_COUNT=1','ADVANCED_PROBE_COMPLETE=True'])
summary = {'scope':'One disarmed Copter 4.7.2 run; advanced typed fence followed by a single legacy return-point write',
           'relay':relay,'uploads':uploads,'acks':acks,'writes':writes,'fetches':fetches,'responses':responses,'counts':counts,'readback':readback,'heartbeats':heartbeats,
           'bad_data_fragments':{'uplink':bad_up,'downlink':bad_down},
           'hashes':{name:sha(out/name) for name in ['probe-source.cs','probe.exe','probe.log','probe-exit.txt']},
           'library_hashes':{name:sha(root/'mission-planner-portable'/name) for name in
                ['MissionPlanner.ArduPilot.dll','MissionPlanner.Utilities.dll','MissionPlanner.Comms.dll','MAVLink.dll','Interfaces.dll','System.ValueTuple.dll','FenceAdvancedWriteProbe.exe.config']}}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print('Typed uploaded:',len(uploads),'legacy writes:',len(writes),'typed readback:',len(readback))
