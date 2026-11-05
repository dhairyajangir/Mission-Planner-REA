"""Check synthetic SERIAL1 signing sessions from independently decoded captures."""
import hashlib,json,os,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'sitl-evidence/python'));os.environ['MAVLINK20']='1'
from pymavlink.dialects.v20 import ardupilotmega
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
key=hashlib.sha256(b'synthetic-signing-seed').digest()
def decode(path):
    parser=ardupilotmega.MAVLink(None);parser.robust_parsing=True;found=[];bad=0
    for b in path.read_bytes():
        m=parser.parse_char(bytes([b]))
        if m is None:continue
        if m.get_type()=='BAD_DATA':bad+=1;continue
        if m.get_type() not in ('SETUP_SIGNING','HEARTBEAT','PARAM_REQUEST_READ','PARAM_VALUE'):continue
        raw=bytes(m.get_msgbuf());d=m.to_dict();d['source']=[m.get_srcSystem(),m.get_srcComponent()]
        d['raw_hex']=raw.hex();d['signed']=raw[0]==253 and bool(raw[2]&1)
        if d['signed']:d['valid_test_key']=hashlib.sha256(key+raw[:-6]).digest()[:6]==raw[-6:]
        found.append(d)
    return found,bad
for case in ('match','missing'):
    out=root/'sitl-evidence'/('signing-serial1-'+case);relay=json.loads((out/'relay-result.json').read_text())
    assert relay['case']==case and not relay['errors'] and relay['closed_by']=='client'
    assert relay['binary_sha256']==sha(root/'sitl-evidence/archive-built/arducopter') and relay['test_key_hex']==key.hex()
    assert all(sha(out/n)==v for n,v in relay['capture_sha256'].items())
    setup,bs=decode(out/'bootstrap-primary-up.bin');p,bp=decode(out/'bootstrap-primary-down.bin');s,bs2=decode(out/'bootstrap-secondary-down.bin')
    up,bu=decode(out/'uplink.bin');down,bd=decode(out/'downlink.bin')
    assert len(setup)==1 and setup[0]['mavpackettype']=='SETUP_SIGNING' and bytes(setup[0]['secret_key'])==key and not setup[0]['signed']
    for name,records in [('primary',p),('secondary',s)]:
        hearts=[m for m in records if m['mavpackettype']=='HEARTBEAT' and m['source']==[1,1]]
        assert hearts and any(not m['signed'] for m in hearts) and any(m['signed'] and m['valid_test_key'] for m in hearts)
        assert all(not(m['base_mode']&128) for m in hearts)
        assert relay['configured_'+name]['raw_hex'] in [m['raw_hex'] for m in hearts]
    hb=[m for m in down if m['mavpackettype']=='HEARTBEAT' and m['source']==[1,1]]
    assert hb and all(m['signed'] and m['valid_test_key'] and not(m['base_mode']&128) for m in hb)
    req=[m for m in up if m['mavpackettype']=='PARAM_REQUEST_READ' and m['param_id']=='LOG_DISARMED']
    resp=[m for m in down if m['mavpackettype']=='PARAM_VALUE' and m['param_id']=='LOG_DISARMED' and m['source']==[1,1]]
    log=(out/'probe.log').read_text(encoding='utf8',errors='replace');assert (out/'probe-exit.txt').read_text().strip()=='0'
    if case=='match':
        assert all(x in log for x in ['CASE=match CANDIDATES=2','OPEN_RETURNED=True ISOPEN=True SELECTED=1:1','ADOPTED=True KEY_NULL=False','PARAM=0','SERIAL1_PROBE_COMPLETE=True'])
        assert req and all(m['signed'] and m['valid_test_key'] for m in req)
        assert resp and any(m['signed'] and m['valid_test_key'] and m['param_value']==0 for m in resp)
    else:
        assert all(x in log for x in ['CASE=missing CANDIDATES=1','OPEN_RETURNED=True ISOPEN=False SELECTED=0:0','ADOPTED=False KEY_NULL=True','Packet failed signature but passed crc','System.InvalidOperationException: Sequence contains no elements','SERIAL1_PROBE_COMPLETE=True'])
        assert not req and not resp
    summary={'case':case,'scope':'Disposable Copter SITL, SERIAL0 setup and Mission Planner original library on SERIAL1',
        'relay':relay,'setup':setup,'bootstrap_primary':p,'bootstrap_secondary':s,'heartbeats':hb,'requests':req,'responses':resp,
        'bad_data_fragments':{'setup':bs,'bootstrap_primary':bp,'bootstrap_secondary':bs2,'uplink':bu,'downlink':bd},
        'hashes':{n:sha(out/n) for n in ['probe-source.cs','probe.exe','probe.log','probe-exit.txt','relay-source.py']},
        'library_hashes':{n:sha(root/'mission-planner-portable'/n) for n in ['MissionPlanner.ArduPilot.dll','MissionPlanner.Utilities.dll','MissionPlanner.Comms.dll','MAVLink.dll','Interfaces.dll','System.ValueTuple.dll','SigningSerial1Probe.exe.config']}}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(case,'heartbeats',len(hb),'requests',len(req),'responses',len(resp))
