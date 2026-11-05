"""Decode failed and successful armed-SITL forwarding experiments."""
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
        if m.get_type() not in ('HEARTBEAT','PARAM_REQUEST_READ','PARAM_VALUE','COMMAND_LONG','COMMAND_ACK','STATUSTEXT'):continue
        d=m.to_dict();d['source']=[m.get_srcSystem(),m.get_srcComponent()];d['raw_hex']=bytes(m.get_msgbuf()).hex();rows.append(d)
    return rows,bad
for mode in ('block','allow'):
  for retry in (False,True):
    case='mavproxy_forward_armed_'+mode+('_retry' if retry else '')
    out=root/'sitl-evidence'/('command-ack-'+case)
    relay=json.loads((out/'relay-result.json').read_text());probe=json.loads((out/'mavproxy-result.json').read_text())
    assert relay['case']==probe['case']==case and relay['binary_sha256']==sha(root/'sitl-evidence/archive-built/arducopter')
    assert probe['source_commit']=='8258c223d8da58f2db71a1c2eabb6834f35e8d8c'
    assert all(sha(out/n)==d for n,d in relay['capture_sha256'].items()) and all(sha(out/n)==d for n,d in probe['artifacts'].items())
    ctrl,bc=decode(out/'control-uplink.bin');ctrl_down,bd=decode(out/'control-downlink.bin');up,bu=decode(out/'to_sitl_output.bin')
    before,bb=decode(out/'udp-before.bin');armed,ba=decode(out/'udp-armed-before.bin');after,bx=decode(out/'udp-after.bin')
    commands=[m for m in ctrl if m['mavpackettype']=='COMMAND_LONG' and m['command']==400]
    acks=[m for m in ctrl_down if m['mavpackettype']=='COMMAND_ACK' and m['command']==400]
    heartbeats=[m for m in ctrl_down if m['mavpackettype']=='HEARTBEAT' and m['source']==[1,1]]
    forwarded=[m for m in up if m['mavpackettype']=='PARAM_REQUEST_READ' and m['source']==[211,77] and m['param_id']=='LOG_DISARMED']
    replies=[m for m in after if m['mavpackettype']=='PARAM_VALUE' and m['source']==[1,1] and m['param_id']=='LOG_DISARMED']
    notices=[m for m in ctrl_down if m['mavpackettype']=='STATUSTEXT' and m['text'].startswith('Arm:')]
    assert heartbeats and commands and all(m['param2']==21196 for m in commands)
    assert probe['configured']==({'mavfwd':'false','mavfwd_disarmed':'true'} if mode=='block' else {'mavfwd':'true','mavfwd_disarmed':'false'})
    log=(out/'mavproxy.log').read_text(encoding='utf8',errors='replace')
    assert 'Received 1431 parameters' in log
    armed_hb=[m for m in armed if m['mavpackettype']=='HEARTBEAT' and m['source']==[1,1]]
    after_hb=[m for m in after if m['mavpackettype']=='HEARTBEAT' and m['source']==[1,1]]
    if retry:
        assert not probe['errors'] and probe['proxy_exit']==1 and not probe.get('forced_terminate')
        assert [m['param1'] for m in commands]==[1,0] and [m['result'] for m in acks]==[0,0]
        assert probe['armed_heartbeat']['base_mode']&128 and not(probe['final_heartbeat']['base_mode']&128)
        assert armed_hb and any(m['base_mode']&128 for m in armed_hb) and after_hb and all(m['base_mode']&128 for m in after_hb)
        assert len(forwarded)==len(replies)==(1 if mode=='allow' else 0)
        if mode=='allow':assert bytes.fromhex(forwarded[0]['raw_hex'])==(out/'request.bin').read_bytes() and replies[0]['param_value']==0
        if relay['errors']:assert len(relay['errors'])==1 and 'ConnectionResetError' in relay['errors'][0]
        else:assert relay['closed_by']=='client'
    else:
        assert len(probe['errors'])==1 and 'heartbeat armed=True' in probe['errors'][0]
        assert [m['param1'] for m in commands]==[1] and any(m['result']==4 for m in acks)
        assert notices and not any(m['base_mode']&128 for m in heartbeats) and not forwarded and not replies
        assert not (out/'request.bin').exists()
    summary={'case':case,'relay':relay,'probe':probe,'commands':commands,'acks':acks,'control_heartbeats':heartbeats,
             'armed_output_heartbeats':armed_hb,'request_window_heartbeats':after_hb,'forwarded':forwarded,'replies':replies,'arm_notices':notices,
             'bad_data_fragments':{'control_up':bc,'control_down':bd,'master_up':bu,'udp_before':bb,'udp_armed':ba,'udp_after':bx},
             'runner_sha256':sha(out/'runner-source.py'),'relay_source_sha256':sha(out/'relay-source.py'),
             'source_inventory_sha256':sha(root/'mission-planner-binary-evidence/mavproxy-source-inventory.json')}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(case,'arm commands',len(commands),'forwarded',len(forwarded),'replies',len(replies),'relay errors',len(relay['errors']))
