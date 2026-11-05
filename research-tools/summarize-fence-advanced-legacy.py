"""Verify advanced typed fence, rejected legacy reads, and subsequent typed readback."""
import hashlib
import json
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parent.parent
out = root / 'sitl-evidence/command-ack-fence_advanced_legacy'
sys.path.insert(0, str(root / 'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega

sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
relay = json.loads((out/'relay-result.json').read_text())
assert relay['case'] == 'fence_advanced_legacy' and not relay['errors'] and relay['closed_by'] == 'client'
assert relay['buffered_bytes_at_close'] == 0 and relay['binary_sha256'] == sha(root/'sitl-evidence/arducopter')
assert all(sha(out/name) == value for name,value in relay['capture_sha256'].items())
def decode(path):
    parser = ardupilotmega.MAVLink(None); parser.robust_parsing = True
    found, bad = [], 0
    for byte in path.read_bytes():
        msg = parser.parse_char(bytes([byte]))
        if msg is None: continue
        if msg.get_type() == 'BAD_DATA': bad += 1; continue
        d = msg.to_dict(); d['source'] = [msg.get_srcSystem(), msg.get_srcComponent()]; found.append(d)
    return found,bad
up,bad_up = decode(out/'to_sitl_output.bin'); down,bad_down = decode(out/'to_client_output.bin')
pick = lambda records,kind: [m for m in records if m['mavpackettype'] == kind]
uploads = [m for m in pick(up,'MISSION_ITEM_INT') if m['mission_type'] == 1]
readback = [m for m in pick(down,'MISSION_ITEM_INT') if m['mission_type'] == 1 and m['source'] == [1,1]]
fetches = pick(up,'FENCE_FETCH_POINT'); responses = pick(down,'FENCE_POINT')
warnings = [m for m in pick(down,'STATUSTEXT') if 'Vehicle contains advanced fences' in m['text'] and m['source'] == [1,1]]
heartbeats = [m for m in pick(down,'HEARTBEAT') if m['source'] == [1,1]]
assert [m['seq'] for m in uploads] == list(range(5)) == [m['seq'] for m in readback]
assert [m['command'] for m in uploads] == [5000,5001,5001,5001,5004]
assert [m['param1'] for m in uploads] == [0,3,3,3,25]
fields = ['seq','command','param1','param2','param3','param4','x','y','z','mission_type']
assert all(all(a[field] == b[field] for field in fields) for a,b in zip(uploads,readback))
assert [m['idx'] for m in fetches] == [0,0,0,0] and not responses and len(warnings) >= 1
assert heartbeats and all(not (m['base_mode'] & 128) for m in heartbeats)
assert (out/'probe-exit.txt').read_text().strip() == '0'
log = (out/'probe.log').read_text(encoding='utf8',errors='replace')
assert all(s in log for s in ['LEGACY_TOTAL=6','LEGACY_ERROR=System.TimeoutException:Timeout on read - getFencePoint','TYPED_COUNT=5','ADVANCED_PROBE_COMPLETE=True'])
summary = {'scope':'One disarmed Copter 4.7.2 run; typed advanced fence then rejected legacy fetch and typed readback',
           'relay':relay,'uploads':uploads,'readback':readback,'fetches':fetches,'responses':responses,
           'warnings':warnings,'heartbeats':heartbeats,'compared_fields':fields,
           'bad_data_fragments':{'uplink':bad_up,'downlink':bad_down},
           'hashes':{name:sha(out/name) for name in ['probe-source.cs','probe.exe','probe.log','probe-exit.txt']},
           'library_hashes':{name:sha(root/'mission-planner-portable'/name) for name in
                ['MissionPlanner.ArduPilot.dll','MissionPlanner.Utilities.dll','MissionPlanner.Comms.dll','MAVLink.dll','Interfaces.dll','System.ValueTuple.dll','FenceAdvancedLegacyProbe.exe.config']}}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print('Typed items:',len(uploads),'legacy fetches:',len(fetches),'warnings:',len(warnings),'readback:',len(readback))
