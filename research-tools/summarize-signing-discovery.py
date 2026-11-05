"""Decode synthetic key-discovery SITL runs; independently verify signatures."""
import hashlib,json,os,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'sitl-evidence/python'));os.environ['MAVLINK20']='1'
from pymavlink.dialects.v20 import ardupilotmega
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
key=hashlib.sha256(b'synthetic-signing-seed').digest()
wrong=hashlib.sha256(b'synthetic-wrong-key').digest()
def decode(path):
    parser=ardupilotmega.MAVLink(None);parser.robust_parsing=True;found=[];bad=0
    for b in path.read_bytes():
        m=parser.parse_char(bytes([b]))
        if m is None:continue
        if m.get_type()=='BAD_DATA':bad+=1;continue
        if m.get_type() not in ('SETUP_SIGNING','PARAM_REQUEST_READ','PARAM_VALUE','HEARTBEAT'):continue
        raw=bytes(m.get_msgbuf());signed=raw[0]==253 and bool(raw[2]&1)
        d=m.to_dict();d['source']=[m.get_srcSystem(),m.get_srcComponent()];d['signed']=signed;d['raw_hex']=raw.hex()
        if signed:
            d['link_id']=raw[-13];d['signature_timestamp']=int.from_bytes(raw[-12:-6],'little')
            for name,candidate in [('test',key),('wrong',wrong),('zero',bytes(32))]:
                d['valid_'+name]=hashlib.sha256(candidate+raw[:-6]).digest()[:6]==raw[-6:]
        found.append(d)
    return found,bad
for case in ('match','missing'):
    out=root/'sitl-evidence'/('command-ack-signing_discovery_'+case)
    relay=json.loads((out/'relay-result.json').read_text())
    assert relay['case']=='signing_discovery_'+case and not relay['errors'] and relay['closed_by']=='client' and relay['buffered_bytes_at_close']==0
    assert relay['binary_sha256']==sha(root/'sitl-evidence/archive-built/arducopter')
    assert all(sha(out/n)==h for n,h in relay['capture_sha256'].items())
    up,bu=decode(out/'to_sitl_output.bin');down,bd=decode(out/'to_client_output.bin')
    setup=[m for m in up if m['mavpackettype']=='SETUP_SIGNING']
    requests=[m for m in up if m['mavpackettype']=='PARAM_REQUEST_READ' and m['param_id']=='LOG_DISARMED']
    responses=[m for m in down if m['mavpackettype']=='PARAM_VALUE' and m['param_id']=='LOG_DISARMED' and m['source']==[1,1]]
    hb=[m for m in down if m['mavpackettype']=='HEARTBEAT' and m['source']==[1,1]]
    assert len(setup)==2 and all(bytes(m['secret_key'])==key and not m['signed'] for m in setup)
    assert requests and not requests[0]['signed'] and any(not m['signed'] and m['param_value']==0 for m in responses)
    assert hb and all(not(m['base_mode']&128) for m in hb) and any(m['signed'] and m['valid_test'] for m in hb)
    assert (out/'probe-exit.txt').read_text().strip()=='0'
    log=(out/'probe.log').read_text(encoding='utf8',errors='replace')
    assert all(x in log for x in ['BEFORE=0','SETUP=True STATE_KEY_NULL=True','DISCOVERY_PROBE_COMPLETE=True'])
    if case=='match':
        assert all(x in log for x in ['CASE=match KEY_CANDIDATES=2','ADOPTED=True KEY_NULL=False','AFTER=0'])
        assert any(m['signed'] and m['valid_test'] for m in requests)
        assert any(m['signed'] and m['valid_test'] and m['param_value']==0 for m in responses)
    else:
        assert all(x in log for x in ['CASE=missing KEY_CANDIDATES=1','ADOPTED=False KEY_NULL=True','AFTER_ERROR=System.TimeoutException:Timeout on read - GetParam','Packet failed signature but passed crc'])
        assert any(m['signed'] and m['valid_zero'] and not m['valid_test'] for m in requests)
        assert any(m['signed'] and m['valid_test'] and m['param_value']==0 for m in responses)
    summary={'scope':'One disposable disarmed Copter SITL; isolated in-process synthetic key registry',
        'case':case,'relay':relay,'synthetic_test_key_hex':key.hex(),'synthetic_wrong_key_hex':wrong.hex(),
        'setup':setup,'requests':requests,'responses':responses,'heartbeats':hb,'bad_data_fragments':{'uplink':bu,'downlink':bd},
        'hashes':{n:sha(out/n) for n in ['probe-source.cs','probe.exe','probe.log','probe-exit.txt']},
        'library_hashes':{n:sha(root/'mission-planner-portable'/n) for n in ['MissionPlanner.ArduPilot.dll','MissionPlanner.Utilities.dll','MissionPlanner.Comms.dll','MAVLink.dll','Interfaces.dll','System.ValueTuple.dll','SigningDiscoveryProbe.exe.config']}}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(case,'requests',len(requests),'responses',len(responses),'signed heartbeats',sum(m['signed'] for m in hb))
