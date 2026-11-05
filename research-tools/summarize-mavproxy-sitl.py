"""Verify pinned MAVProxy checkout and independently decode forwarded telemetry."""
import collections,hashlib,json,os,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'sitl-evidence/python'));os.environ['MAVLINK20']='1'
from pymavlink.dialects.v20 import ardupilotmega
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
inventory=json.loads((root/'mission-planner-binary-evidence/mavproxy-source-inventory.json').read_text())
assert inventory['commit']=='8258c223d8da58f2db71a1c2eabb6834f35e8d8c'
assert inventory['counts']=={'exact':87,'crlf_normalized':389,'mismatch':0,'missing':0,'not_checked_special_mode':1}
assert [r['path'] for r in inventory['files'] if r['status']=='not_checked_special_mode']==['MAVProxy/modules/mavproxy_cesium']
for case in ('mavproxy-sitl-smoke','mavproxy-sitl-smoke-2','mavproxy-sitl-smoke-3'):
    out=root/'sitl-evidence'/case;r=json.loads((out/'result.json').read_text())
    assert not r['errors'] and r['source_commit']==inventory['commit']
    assert r['binary_sha256']==sha(root/'sitl-evidence/archive-built/arducopter')
    assert all(sha(out/n)==v for n,v in r['artifacts'].items())
    assert r['commands']==['param show LOG_DISARMED','wp list','exit'] and r['forwarded_datagrams']>0
    parser=ardupilotmega.MAVLink(None);parser.robust_parsing=True;messages=[];bad=0
    for b in (out/'forwarded.bin').read_bytes():
        m=parser.parse_char(bytes([b]))
        if m is None:continue
        if m.get_type()=='BAD_DATA':bad+=1;continue
        d=m.to_dict();d['source']=[m.get_srcSystem(),m.get_srcComponent()];messages.append(d)
    hb=[m for m in messages if m['mavpackettype']=='HEARTBEAT' and m['source']==[1,1]]
    assert hb and all(not(m['base_mode'] & 128) for m in hb)
    types=collections.Counter(m['mavpackettype'] for m in messages)
    log=(out/'mavproxy.log').read_text(encoding='utf8',errors='replace')
    assert all(x in log for x in ['Detected vehicle 1:1 on link 0','Received 1431 parameters','LOG_DISARMED     0.0','Requesting 0 waypoints'])
    if case=='mavproxy-sitl-smoke':assert "Unknown command 'exit'" in log and r.get('forced_terminate')
    if case=='mavproxy-sitl-smoke-2':assert r.get('forced_terminate')
    if case=='mavproxy-sitl-smoke-3':assert r.get('stdin_closed') and not r.get('forced_terminate') and r['proxy_exit']==1
    summary={'scope':'One local disarmed Copter SITL run; MAVProxy source with param and wp modules',
             'result':r,'source_inventory_sha256':sha(root/'mission-planner-binary-evidence/mavproxy-source-inventory.json'),
             'runner_source_sha256':sha(out/'runner-source.py'),'heartbeat_count':len(hb),'heartbeats':hb,
             'forwarded_message_counts':dict(types),'bad_data_fragments':bad}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(case,'heartbeats',len(hb),'frames',sum(types.values()),'bad',bad,'exit',r['proxy_exit'])
