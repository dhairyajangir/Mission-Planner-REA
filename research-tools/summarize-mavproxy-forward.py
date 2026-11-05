"""Verify local MAVProxy forwarding settings with captured packets."""
import hashlib,json,os,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(root/'sitl-evidence/python'));os.environ['MAVLINK20']='1'
from pymavlink.dialects.v20 import ardupilotmega
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def decode(path):
    parser=ardupilotmega.MAVLink(None);parser.robust_parsing=True;rows=[];bad=0
    for b in path.read_bytes():
        m=parser.parse_char(bytes([b]))
        if m is None:continue
        if m.get_type()=='BAD_DATA':bad+=1;continue
        if m.get_type() not in ('HEARTBEAT','PARAM_REQUEST_READ','PARAM_VALUE'):continue
        d=m.to_dict();d['source']=[m.get_srcSystem(),m.get_srcComponent()];d['raw_hex']=bytes(m.get_msgbuf()).hex();rows.append(d)
    return rows,bad
for case,settings,forward in [('default',('true','true'),True),('disabled',('false','false'),False),('disarmed',('false','true'),True)]:
    out=root/'sitl-evidence'/('command-ack-mavproxy_forward_'+case)
    relay=json.loads((out/'relay-result.json').read_text());probe=json.loads((out/'mavproxy-result.json').read_text())
    assert relay['case']==probe['case']=='mavproxy_forward_'+case and relay['binary_sha256']==sha(root/'sitl-evidence/archive-built/arducopter')
    assert probe['source_commit']=='8258c223d8da58f2db71a1c2eabb6834f35e8d8c' and not probe['errors'] and probe['proxy_exit']==1 and not probe.get('forced_terminate')
    assert all(sha(out/n)==v for n,v in relay['capture_sha256'].items()) and all(sha(out/n)==v for n,v in probe['artifacts'].items())
    if case in ('default','disabled'):
        assert len(relay['errors'])==1 and 'ConnectionResetError' in relay['errors'][0]
    else:assert not relay['errors'] and relay['closed_by']=='client' and relay['buffered_bytes_at_close']==0
    request,br=decode(out/'request.bin');up,bu=decode(out/'to_sitl_output.bin');down,bd=decode(out/'udp-after.bin');before,bb=decode(out/'udp-before.bin')
    assert len(request)==1 and request[0]['mavpackettype']=='PARAM_REQUEST_READ' and request[0]['source']==[211,77] and request[0]['param_id']=='LOG_DISARMED'
    forwarded=[m for m in up if m['mavpackettype']=='PARAM_REQUEST_READ' and m['source']==[211,77] and m['param_id']=='LOG_DISARMED']
    responses=[m for m in down if m['mavpackettype']=='PARAM_VALUE' and m['source']==[1,1] and m['param_id']=='LOG_DISARMED']
    hb=[m for m in before+down if m['mavpackettype']=='HEARTBEAT' and m['source']==[1,1]]
    assert hb and all(not(m['base_mode']&128) for m in hb)
    assert len(forwarded)==(1 if forward else 0) and len(responses)==(1 if forward else 0)
    if forward:assert forwarded[0]['raw_hex']==request[0]['raw_hex'] and responses[0]['param_value']==0
    log=(out/'mavproxy.log').read_text(encoding='utf8',errors='replace')
    assert 'mavfwd '+settings[0].capitalize() in log and 'mavfwd_disarmed '+settings[1].capitalize() in log
    assert 'Received 1431 parameters' in log
    summary={'scope':'One disarmed Copter SITL, pinned MAVProxy source and one read-only downstream UDP request',
             'case':case,'relay':relay,'probe':probe,'request':request[0],'forwarded':forwarded,'responses':responses,'heartbeats':hb,
             'bad_data_fragments':{'request':br,'uplink':bu,'udp_after':bd,'udp_before':bb},
             'runner_sha256':sha(out/'runner-source.py'),'relay_source_sha256':sha(out/'relay-source.py'),
             'source_inventory_sha256':sha(root/'mission-planner-binary-evidence/mavproxy-source-inventory.json')}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(case,'forwarded',len(forwarded),'responses',len(responses),'relay errors',len(relay['errors']))
