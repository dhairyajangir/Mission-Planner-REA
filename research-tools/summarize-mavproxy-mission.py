"""Decode normal and lost-ACK MAVProxy mission uploads, including failed attempts."""
import hashlib,json,os,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'sitl-evidence/python'));os.environ['MAVLINK20']='1'
from pymavlink.dialects.v20 import ardupilotmega
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def decode(path):
    p=ardupilotmega.MAVLink(None);p.robust_parsing=True;rows=[];bad=0
    for b in path.read_bytes():
        m=p.parse_char(bytes([b]))
        if m is None:continue
        if m.get_type()=='BAD_DATA':bad+=1;continue
        if m.get_type() not in ('HEARTBEAT','MISSION_COUNT','MISSION_ITEM_INT','MISSION_ACK','MISSION_REQUEST','MISSION_REQUEST_INT'):continue
        d=m.to_dict();d['source']=[m.get_srcSystem(),m.get_srcComponent()];rows.append(d)
    return rows,bad
pick=lambda rows,t:[m for m in rows if m['mavpackettype']==t]
for case in ('mavproxy_mission_normal','mavproxy_mission_drop_ack','mavproxy_mission_normal_retry','mavproxy_mission_drop_ack_retry'):
    out=root/'sitl-evidence'/('command-ack-'+case)
    relay=json.loads((out/'relay-result.json').read_text());probe=json.loads((out/'mavproxy-result.json').read_text())
    assert relay['case']==probe['case']==case and relay['binary_sha256']==sha(root/'sitl-evidence/archive-built/arducopter')
    assert probe['source_commit']=='8258c223d8da58f2db71a1c2eabb6834f35e8d8c'
    assert all(sha(out/n)==v for n,v in relay['capture_sha256'].items())
    assert all(sha(out/n)==v for n,v in probe['artifacts'].items())
    up,bu=decode(out/'to_sitl_output.bin');incoming,bi=decode(out/'to_client_input.bin');down,bd=decode(out/'to_client_output.bin');dropped,bx=decode(out/'dropped.bin')
    items=pick(up,'MISSION_ITEM_INT');acks=pick(incoming,'MISSION_ACK');delivered=pick(down,'MISSION_ACK')
    hb=[m for m in incoming if m['mavpackettype']=='HEARTBEAT' and m['source']==[1,1]]
    assert hb and all(not(m['base_mode']&128) for m in hb)
    log=(out/'mavproxy.log').read_text(encoding='utf8',errors='replace')
    summary={'case':case,'relay':relay,'probe':probe,'uploads':items,'acks':acks,'delivered_acks':delivered,'dropped':dropped,'heartbeats':hb,
             'bad_data_fragments':{'uplink':bu,'incoming':bi,'delivered':bd,'dropped':bx},
             'runner_sha256':sha(out/'runner-source.py'),'relay_source_sha256':sha(out/'relay-source.py'),
             'source_inventory_sha256':sha(root/'mission-planner-binary-evidence/mavproxy-source-inventory.json')}
    if not case.endswith('_retry'):
        assert len(probe['errors'])==1 and 'MAVProxy did not report sending mission' in probe['errors'][0]
        assert relay['errors'] and 'ConnectionResetError' in relay['errors'][0] and 'usage: wp load FILENAME' in log
        assert not items
    else:
        assert not probe['errors'] and not relay['errors'] and relay['closed_by']=='client' and relay['buffered_bytes_at_close']==0
        assert probe['commands']==['wp load input.waypoints','exit'] and not probe.get('forced_terminate') and probe['proxy_exit']==1
        assert all(s in log for s in ['Loaded 2 waypoints from input.waypoints','Sent all 2 waypoints'])
        counts=pick(up,'MISSION_COUNT');requests=pick(incoming,'MISSION_REQUEST')+pick(incoming,'MISSION_REQUEST_INT')
        assert len(counts)==1 and counts[0]['count']==2 and [m['seq'] for m in items]==[0,1] and [m['seq'] for m in requests]==[0,1]
        assert len(acks)==1 and acks[0]['type']==0 and acks[0]['source']==[1,1]
        if 'drop_ack' in case:
            assert relay['dropped_mission_acks']==1 and dropped==acks and not delivered
        else:assert not dropped and delivered==acks
        read,bread=decode(out/'independent-downlink.bin');counts2=pick(read,'MISSION_COUNT');readback=pick(read,'MISSION_ITEM_INT')
        assert len(counts2)==1 and counts2[0]['count']==2 and [m['seq'] for m in readback]==[0,1]
        assert all(m['source']==[1,1] for m in readback)
        fields=['seq','frame','command','param1','param2','param3','param4','x','y','z','mission_type']
        assert all(items[1][f]==readback[1][f] for f in fields)
        assert (readback[1]['x'],readback[1]['y'],readback[1]['z'],readback[1]['param1'])==(-353625000,1491660000,25,2)
        assert (items[0]['x'],items[0]['y'],items[0]['z'])!= (readback[0]['x'],readback[0]['y'],readback[0]['z'])
        summary.update({'counts':counts,'requests':requests,'independent_counts':counts2,'readback':readback,'compared_waypoint_fields':fields,'independent_bad_data_fragments':bread})
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(case,'uploaded',len(items),'acks',len(acks),'delivered',len(delivered))
