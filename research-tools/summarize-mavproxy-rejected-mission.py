"""Decode MAVProxy valid upload and rejected invalid replacement with independent readback."""
import hashlib,json,os,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent;out=root/'sitl-evidence/command-ack-mavproxy_mission_reject'
sys.path.insert(0,str(root/'sitl-evidence/python'));os.environ['MAVLINK20']='1'
from pymavlink.dialects.v20 import ardupilotmega
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
relay=json.loads((out/'relay-result.json').read_text());probe=json.loads((out/'mavproxy-result.json').read_text())
assert relay['case']==probe['case']=='mavproxy_mission_reject' and not relay['errors'] and not probe['errors']
assert relay['closed_by']=='client' and relay['buffered_bytes_at_close']==0
assert relay['binary_sha256']==sha(root/'sitl-evidence/archive-built/arducopter')
assert all(sha(out/n)==v for n,v in relay['capture_sha256'].items()) and all(sha(out/n)==v for n,v in probe['artifacts'].items())
def decode(path):
    parser=ardupilotmega.MAVLink(None);parser.robust_parsing=True;found=[];bad=0
    for b in path.read_bytes():
        m=parser.parse_char(bytes([b]))
        if m is None:continue
        if m.get_type()=='BAD_DATA':bad+=1;continue
        if m.get_type() not in ('HEARTBEAT','MISSION_COUNT','MISSION_ITEM_INT','MISSION_ACK','MISSION_REQUEST','MISSION_REQUEST_INT'):continue
        d=m.to_dict();d['source']=[m.get_srcSystem(),m.get_srcComponent()];found.append(d)
    return found,bad
pick=lambda rows,t:[m for m in rows if m['mavpackettype']==t]
up,bu=decode(out/'to_sitl_output.bin');down,bd=decode(out/'to_client_output.bin')
baseline,bb=decode(out/'baseline-downlink.bin');after,ba=decode(out/'after_invalid-downlink.bin')
uploads=pick(up,'MISSION_ITEM_INT');counts=pick(up,'MISSION_COUNT');acks=pick(down,'MISSION_ACK')
assert len(counts)==2 and [m['count'] for m in counts]==[2,2]
assert [m['seq'] for m in uploads]==[0,1,0,1] and [m['command'] for m in uploads]==[16,16,16,65535]
assert [m['type'] for m in acks]==[0,3] and all(m['source']==[1,1] for m in acks)
base_items=pick(baseline,'MISSION_ITEM_INT');after_items=pick(after,'MISSION_ITEM_INT')
assert [m['seq'] for m in base_items]==[0,1]==[m['seq'] for m in after_items]
fields=['seq','frame','command','param1','param2','param3','param4','x','y','z','mission_type']
assert all(all(a[f]==b[f] for f in fields) for a,b in zip(base_items,after_items))
assert (after_items[1]['command'],after_items[1]['x'],after_items[1]['y'],after_items[1]['z'])==(16,-353625000,1491660000,25)
hb=[m for m in down if m['mavpackettype']=='HEARTBEAT' and m['source']==[1,1]]
assert hb and all(not(m['base_mode']&128) for m in hb)
log=(out/'mavproxy.log').read_text(encoding='utf8',errors='replace')
assert log.count('Sent all 2 waypoints')==2 and 'Got MISSION_ACK: TYPE_MISSION: ACCEPTED' in log and 'Got MISSION_ACK: TYPE_MISSION: UNSUPPORTED' in log
assert log.rfind('Sent all 2 waypoints') < log.rfind('Got MISSION_ACK: TYPE_MISSION: UNSUPPORTED')
assert probe['commands']==['wp load baseline.waypoints','wp load invalid.waypoints','exit'] and probe['proxy_exit']==1 and not probe.get('forced_terminate')
summary={'scope':'One disarmed Copter SITL run; MAVProxy valid mission followed by unsupported replacement',
         'relay':relay,'probe':probe,'counts':counts,'uploads':uploads,'acks':acks,'baseline_readback':base_items,'after_readback':after_items,
         'compared_fields':fields,'heartbeats':hb,'bad_data_fragments':{'uplink':bu,'downlink':bd,'baseline':bb,'after':ba},
         'runner_sha256':sha(out/'runner-source.py'),'relay_source_sha256':sha(out/'relay-source.py'),
         'source_inventory_sha256':sha(root/'mission-planner-binary-evidence/mavproxy-source-inventory.json')}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print('ACKs accepted then unsupported; independently read selected mission fields unchanged')
