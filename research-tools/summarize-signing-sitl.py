"""Independently decode and check synthetic-key signed SITL exchange."""
import hashlib,json,os,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent
out=root/'sitl-evidence/command-ack-signing_sitl'
sys.path.insert(0,str(root/'sitl-evidence/python'));os.environ['MAVLINK20']='1'
from pymavlink.dialects.v20 import ardupilotmega
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
key=bytes(range(32));relay=json.loads((out/'relay-result.json').read_text())
assert relay['case']=='signing_sitl' and not relay['errors'] and relay['closed_by']=='client' and relay['buffered_bytes_at_close']==0
assert relay['binary_sha256']==sha(root/'sitl-evidence/archive-built/arducopter')
assert all(sha(out/n)==h for n,h in relay['capture_sha256'].items())
def decode(path):
    parser=ardupilotmega.MAVLink(None);parser.robust_parsing=True;found=[];bad=0
    for b in path.read_bytes():
        m=parser.parse_char(bytes([b]))
        if m is None:continue
        if m.get_type()=='BAD_DATA':bad+=1;continue
        if m.get_type() not in ('SETUP_SIGNING','PARAM_REQUEST_READ','PARAM_VALUE','HEARTBEAT','STATUSTEXT'):continue
        raw=bytes(m.get_msgbuf());signed=raw[0]==253 and bool(raw[2]&1)
        d=m.to_dict();d['source']=[m.get_srcSystem(),m.get_srcComponent()];d['signed']=signed;d['raw_hex']=raw.hex()
        if signed:
            d['link_id']=raw[-13];d['signature_timestamp']=int.from_bytes(raw[-12:-6],'little')
            d['valid_test_key']=hashlib.sha256(key+raw[:-6]).digest()[:6]==raw[-6:]
            d['valid_zero_key']=hashlib.sha256(bytes(32)+raw[:-6]).digest()[:6]==raw[-6:]
        found.append(d)
    return found,bad
up,bad_up=decode(out/'to_sitl_output.bin');down,bad_down=decode(out/'to_client_output.bin')
setup=[m for m in up if m['mavpackettype']=='SETUP_SIGNING']
requests=[m for m in up if m['mavpackettype']=='PARAM_REQUEST_READ' and m['param_id']=='LOG_DISARMED']
responses=[m for m in down if m['mavpackettype']=='PARAM_VALUE' and m['param_id']=='LOG_DISARMED' and m['source']==[1,1]]
hb=[m for m in down if m['mavpackettype']=='HEARTBEAT' and m['source']==[1,1]]
assert len(setup)==2 and all(bytes(m['secret_key'])==key and not m['signed'] for m in setup)
assert len(requests)==2 and not requests[0]['signed'] and requests[1]['signed'] and requests[1]['valid_test_key']
assert any(not m['signed'] and m['param_value']==0 for m in responses)
assert any(m['signed'] and m['valid_test_key'] and m['param_value']==0 for m in responses)
assert hb and all(not(m['base_mode']&128) for m in hb) and any(m['signed'] and m['valid_test_key'] for m in hb)
zero_status=[m for m in up if m['mavpackettype']=='STATUSTEXT' and m['signed'] and m['valid_zero_key'] and not m['valid_test_key']]
assert len(zero_status)==1
assert up.index(zero_status[0]) < up.index(requests[0]) < up.index(setup[0]) < up.index(requests[1])
log=(out/'probe.log').read_text(encoding='utf8',errors='replace')
assert (out/'probe-exit.txt').read_text().strip()=='0'
assert all(s in log for s in ['BEFORE=0','SETUP_RETURN=True STATE_SIGNING=True','AFTER=0','SIGNING_SITL_COMPLETE=True'])
summary={'scope':'One disposable disarmed source-built Copter SITL; explicit synthetic key injection in Mission Planner state',
         'relay':relay,'synthetic_key_hex':key.hex(),'setup':setup,'requests':requests,'responses':responses,'heartbeats':hb,'zero_key_status':zero_status,
         'bad_data_fragments':{'uplink':bad_up,'downlink':bad_down},
         'hashes':{n:sha(out/n) for n in ['probe-source.cs','probe.exe','probe.log','probe-exit.txt']},
         'library_hashes':{n:sha(root/'mission-planner-portable'/n) for n in ['MissionPlanner.ArduPilot.dll','MissionPlanner.Utilities.dll','MissionPlanner.Comms.dll','MAVLink.dll','Interfaces.dll','System.ValueTuple.dll','SigningSitlProbe.exe.config']}}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print('Setup messages',len(setup),'valid signed request and response',sum(m.get('valid_test_key',False) for m in requests),sum(m.get('valid_test_key',False) for m in responses),'zero-key status',len(zero_status))
