"""Decode partial-write and final-ACK loss experiments, including failed injections."""
import hashlib,json,os,struct,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'sitl-evidence/python'));os.environ['MAVLINK20']='1'
from pymavlink.dialects.v20 import ardupilotmega
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def decode(path):
    p=ardupilotmega.MAVLink(None);p.robust_parsing=True;out=[];bad=0
    for b in path.read_bytes():
        m=p.parse_char(bytes([b]))
        if m is None:continue
        if m.get_type()=='BAD_DATA':bad+=1;continue
        d=m.to_dict();d['source']=[m.get_srcSystem(),m.get_srcComponent()]
        if m.get_type()=='FILE_TRANSFER_PROTOCOL':
            payload=bytes(m.payload);h=struct.unpack('<HBBBBBBI',payload[:12])
            d['ftp']={'seq':h[0],'session':h[1],'opcode':h[2],'size':h[3],'request_opcode':h[4],'offset':h[7],'data_hex':payload[12:12+h[3]].hex()}
        out.append(d)
    return out,bad
pick=lambda rows,kind:[m for m in rows if m['mavpackettype']==kind]
for case in ('fence_mavftp_partial','fence_mavftp_last_ack','fence_mavftp_last_ack_fixed','fence_mavftp_last_ack_retry'):
    out=root/'sitl-evidence'/('command-ack-'+case);relay=json.loads((out/'relay-result.json').read_text())
    assert relay['case']==case and not relay['errors'] and relay['closed_by']=='client' and relay['buffered_bytes_at_close']==0
    assert relay['binary_sha256']==sha(root/'sitl-evidence/archive-built/arducopter')
    assert all(sha(out/n)==h for n,h in relay['capture_sha256'].items())
    up,bu=decode(out/'to_sitl_input.bin');delivered,bd=decode(out/'to_sitl_output.bin')
    downin,bdi=decode(out/'to_client_input.bin');down,bdo=decode(out/'to_client_output.bin');dropped,bx=decode(out/'dropped.bin')
    ftp_in=pick(up,'FILE_TRANSFER_PROTOCOL');ftp_delivered=pick(delivered,'FILE_TRANSFER_PROTOCOL')
    ftp_downin=pick(downin,'FILE_TRANSFER_PROTOCOL');ftp_down=pick(down,'FILE_TRANSFER_PROTOCOL')
    baseline=[m for m in pick(up,'MISSION_ITEM_INT') if m['mission_type']==1]
    readback=[m for m in pick(down,'MISSION_ITEM_INT') if m['mission_type']==1 and m['source']==[1,1]]
    hb=[m for m in pick(down,'HEARTBEAT') if m['source']==[1,1]]
    assert [m['seq'] for m in baseline]==list(range(4))==[m['seq'] for m in readback]
    assert [m['param1'] for m in baseline]==[3,3,3,15] and hb and all(not(m['base_mode']&128) for m in hb)
    assert (out/'probe-exit.txt').read_text().strip()=='0'
    log=(out/'probe.log').read_text(encoding='utf8',errors='replace')
    assert all(x in log for x in ['FTP_UPLOAD_RETURNED=True BYTES=162','MISSION_COUNT=4','DROP_PROBE_COMPLETE=True'])
    packet=(out/'upload.dat').read_bytes();assert struct.unpack('<5H',packet[:10])==(0x763d,1,0,0,4)
    names=['param1','param2','param3','param4','x','y','z','seq','command','target_system','target_component','frame','current','autocontinue','mission_type']
    replacement=[dict(zip(names,struct.unpack('<ffffiifHHBBBBBB',packet[10+i*38:48+i*38]))) for i in range(4)]
    fields=['command','param1','param2','param3','param4','x','y','z']
    if case=='fence_mavftp_partial':
        assert len(dropped)==1 and dropped[0]['ftp']['opcode']==7 and dropped[0]['ftp']['offset']==80
        assert dropped == [m for m in ftp_in if m['ftp']['opcode']==7 and m['ftp']['offset']==80]
        assert [m['ftp']['offset'] for m in ftp_delivered if m['ftp']['opcode']==7]==[0,160]
        assert any(m['ftp']['opcode']==128 and m['ftp']['request_opcode']==7 and m['ftp']['offset']==160 for m in ftp_down)
        assert all(all(a[f]==b[f] for f in fields) for a,b in zip(baseline,readback))
    else:
        assert all(all(a[f]==b[f] for f in fields) for a,b in zip(replacement,readback))
        if case in ('fence_mavftp_last_ack','fence_mavftp_last_ack_fixed'):
            assert not dropped
        else:
            assert dropped and all(m['ftp']['opcode']==128 and m['ftp']['request_opcode']==7 and m['ftp']['offset']==160 for m in dropped)
            assert len(dropped)==relay['dropped_ftp_packets']==30
            assert dropped == [m for m in ftp_downin if m['ftp']['opcode']==128 and m['ftp']['request_opcode']==7 and m['ftp']['offset']==160]
            assert [m['ftp']['offset'] for m in ftp_delivered if m['ftp']['opcode']==7][:3]==[0,80,160]
            assert sum(m['ftp']['opcode']==7 and m['ftp']['offset']==160 for m in ftp_delivered)==30
            assert not any(m['ftp']['opcode']==128 and m['ftp']['request_opcode']==7 and m['ftp']['offset']==160 for m in ftp_down)
    summary={'case':case,'relay':relay,'baseline':baseline,'replacement':replacement,'readback':readback,'compared_fields':fields,
             'ftp_in':ftp_in,'ftp_delivered':ftp_delivered,'ftp_down_input':ftp_downin,'ftp_down':ftp_down,'dropped':dropped,'heartbeats':hb,
             'bad_data_fragments':{'uplink':bu,'delivered':bd,'downlink_input':bdi,'downlink':bdo,'dropped':bx},
             'hashes':{n:sha(out/n) for n in ['probe-source.cs','probe.exe','probe.log','probe-exit.txt','upload.dat']},
             'library_hashes':{n:sha(root/'mission-planner-portable'/n) for n in ['MissionPlanner.ArduPilot.dll','MissionPlanner.Utilities.dll','MissionPlanner.Comms.dll','MAVLink.dll','Interfaces.dll','System.ValueTuple.dll','FenceMavftpDropProbe.exe.config']}}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(case,'drops',len(dropped),'radius',readback[3]['param1'])
