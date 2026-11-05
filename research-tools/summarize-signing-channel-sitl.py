"""Re-decode byte-bounded signing experiment windows and validate signatures."""
import hashlib,json,os,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'sitl-evidence/python'));os.environ['MAVLINK20']='1'
from pymavlink.dialects.v20 import ardupilotmega
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def decode(data):
    parser=ardupilotmega.MAVLink(None);parser.robust_parsing=True;out=[];bad=0
    for b in data:
        m=parser.parse_char(bytes([b]))
        if m is None:continue
        if m.get_type()=='BAD_DATA':bad+=1;continue
        d=m.to_dict();d['source']=[m.get_srcSystem(),m.get_srcComponent()];d['raw_hex']=bytes(m.get_msgbuf()).hex();out.append(d)
    return out,bad
def sig(raw,key):return raw[0]==253 and bool(raw[2]&1) and hashlib.sha256(key+raw[:-6]).digest()[:6]==raw[-6:]
first=root/'sitl-evidence/signing-channel-sitl';old=json.loads((first/'result.json').read_text())
assert not old['errors'] and all(sha(first/n)==digest for n,digest in old['capture_sha256'].items())
assert {(e['channel'],e['case']):len(e['responses']) for e in old['events'] if e['case']!='initial'} == {
    ('channel0','unsigned'):1,('channel0','bad_signature'):1,('channel0','valid'):1,('channel0','replay'):1,
    ('channel1','unsigned'):0,('channel1','bad_signature'):0,('channel1','valid'):1,('channel1','replay'):0}
out=root/'sitl-evidence/signing-channel-sitl-2';r=json.loads((out/'result.json').read_text())
assert not r['errors'] and r['binary_sha256']==sha(root/'sitl-evidence/archive-built/arducopter')
assert all(sha(out/n)==digest for n,digest in r['capture_sha256'].items())
key=hashlib.sha256(b'synthetic-channel-signing-key').digest();wrong=hashlib.sha256(b'synthetic-channel-wrong-key').digest()
assert r['test_key_hex']==key.hex() and r['wrong_key_hex']==wrong.hex()
log=(out/'sitl.log').read_text(errors='replace')
assert all(s in log for s in ('SERIAL0 on TCP port 7560','SERIAL1 on TCP port 7562','New connection on SERIAL1'))
events={};bad={}
for e in r['events']:
    ch=e['channel'];case=e['case']
    if case=='initial':
        assert e['heartbeats'] and all(not(m['base_mode']&128) for m in e['heartbeats']);continue
    uplink=(out/(ch+'-uplink.bin')).read_bytes();downlink=(out/(ch+'-downlink.bin')).read_bytes()
    packet=bytes.fromhex(e['packet_hex']);assert uplink[e['uplink_start']:e['uplink_end']]==packet
    requests,request_bad=decode(packet)
    assert request_bad==0 and len(requests)==1 and requests[0]['mavpackettype']=='PARAM_REQUEST_READ' and requests[0]['param_id']=='LOG_DISARMED'
    if case=='unsigned':assert packet[0]==253 and not(packet[2]&1)
    if case=='bad_signature':assert sig(packet,wrong) and not sig(packet,key)
    if case in ('valid','replay'):assert sig(packet,key)
    parsed,fragments=decode(downlink[e['downlink_start']:e['downlink_end']]);bad[ch+'/'+case]=fragments
    responses=[m for m in parsed if m['mavpackettype']=='PARAM_VALUE' and m['param_id']=='LOG_DISARMED' and m['source']==[1,1]]
    assert [m['raw_hex'] for m in responses]==[m['raw_hex'] for m in e['responses']]
    assert all(m['param_value']==0 and sig(bytes.fromhex(m['raw_hex']),key) for m in responses)
    events[(ch,case)]={'request_hex':packet.hex(),'responses':responses,'uplink_start':e['uplink_start'],'uplink_end':e['uplink_end'],'downlink_start':e['downlink_start'],'downlink_end':e['downlink_end']}
expected={('channel0','unsigned'):1,('channel0','bad_signature'):1,('channel0','valid'):1,('channel0','replay'):1,
          ('channel1','unsigned'):0,('channel1','bad_signature'):0,('channel1','valid'):1,('channel1','replay'):0}
assert {k:len(v['responses']) for k,v in events.items()}==expected
assert all(events[(ch,'valid')]['request_hex']==events[(ch,'replay')]['request_hex'] for ch in ('channel0','channel1'))
summary={'scope':'Two disposable Copter SITL runs; standalone synthetic MAVLink client; disarmed',
         'binary_sha256':r['binary_sha256'],'test_key_hex':key.hex(),'wrong_key_hex':wrong.hex(),
         'first_result_sha256':sha(first/'result.json'),'second_result_sha256':sha(out/'result.json'),
         'captures':r['capture_sha256'],'events':{a+'/'+b:v for (a,b),v in events.items()},'window_bad_data_fragments':bad}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print('Two runs: endpoint 0 answered 4/4; endpoint 1 answered only signed non-replay request')
