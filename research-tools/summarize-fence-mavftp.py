"""Independently decode MAVFTP frames and packed fence files from two harness runs."""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega
sha=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def decode(path):
    parser=ardupilotmega.MAVLink(None);parser.robust_parsing=True
    records=[];bad=0
    for b in path.read_bytes():
        m=parser.parse_char(bytes([b]))
        if m is None: continue
        if m.get_type()=='BAD_DATA': bad+=1;continue
        d=m.to_dict();d['source']=[m.get_srcSystem(),m.get_srcComponent()]
        if m.get_type()=='FILE_TRANSFER_PROTOCOL':
            payload=bytes(m.payload);h=struct.unpack('<HBBBBBBI',payload[:12])
            d['ftp']={'seq':h[0],'session':h[1],'opcode':h[2],'size':h[3],'request_opcode':h[4],'burst_complete':h[5],'offset':h[7], 'data_hex':payload[12:12+h[3]].hex()}
        records.append(d)
    return records,bad
def packed(path):
    b=path.read_bytes();head=struct.unpack('<5H',b[:10]); assert head==(0x763d,1,0,0,4) and len(b)==162
    names=['param1','param2','param3','param4','x','y','z','seq','command','target_system','target_component','frame','current','autocontinue','mission_type']
    return [dict(zip(names,struct.unpack('<ffffiifHHBBBBBB',b[10+i*38:48+i*38]))) for i in range(4)]
def pick(rows,kind):return [m for m in rows if m['mavpackettype']==kind]
for case in ('fence_mavftp','fence_mavftp_pumped'):
    out=root/'sitl-evidence'/('command-ack-'+case);relay=json.loads((out/'relay-result.json').read_text())
    assert relay['case']==case and not relay['errors'] and relay['closed_by']=='client' and relay['buffered_bytes_at_close']==0
    assert relay['binary_sha256']==sha(root/'sitl-evidence/archive-built/arducopter')
    assert all(sha(out/name)==digest for name,digest in relay['capture_sha256'].items())
    up,bad_up=decode(out/'to_sitl_output.bin');down,bad_down=decode(out/'to_client_output.bin')
    ftp_up=pick(up,'FILE_TRANSFER_PROTOCOL');ftp_down=pick(down,'FILE_TRANSFER_PROTOCOL')
    hb=[m for m in pick(down,'HEARTBEAT') if m['source']==[1,1]]
    assert hb and all(not(m['base_mode'] & 128) for m in hb)
    upload=packed(out/'upload.dat');log=(out/'probe.log').read_text(encoding='utf8',errors='replace')
    assert [m['command'] for m in upload]==[5001,5001,5001,5004]
    assert [m['param1'] for m in upload]==[3,3,3,25]
    assert 'FTP_UPLOAD_RETURNED=True BYTES=162' in log
    summary={'case':case,'relay':relay,'ftp_up':ftp_up,'ftp_down':ftp_down,'heartbeats':hb,'upload':upload,
             'bad_data_fragments':{'uplink':bad_up,'downlink':bad_down},
             'hashes':{name:sha(out/name) for name in ['probe-source.cs','probe.exe','probe.log','probe-exit.txt','upload.dat']},
             'library_hashes':{name:sha(root/'mission-planner-portable'/name) for name in
                 ['MissionPlanner.ArduPilot.dll','MissionPlanner.Utilities.dll','MissionPlanner.Comms.dll','MAVLink.dll','Interfaces.dll','System.ValueTuple.dll','FenceMavftpProbe.exe.config']}}
    if case=='fence_mavftp':
        assert (out/'probe-exit.txt').read_text().strip()=='1' and 'MISSION_COUNT=0' in log and 'ERROR=System.NullReferenceException' in log
        assert not (out/'download.dat').exists()
    else:
        assert (out/'probe-exit.txt').read_text().strip()=='0'
        assert all(s in log for s in ['MISSION_COUNT=4','FTP_DOWNLOAD_BYTES=162 TYPE=FENCE START=0 COUNT=4','FTP_PROBE_COMPLETE=True'])
        assert [m['ftp']['opcode'] for m in ftp_up]==[2,6,7,7,7,2,2,4,15]
        assert bytes.fromhex(ftp_up[1]['ftp']['data_hex'])==b'@MISSION/fence.dat'
        writes=[m['ftp'] for m in ftp_up if m['ftp']['opcode']==7]
        assert [m['offset'] for m in writes]==[0,80,160]
        assert b''.join(bytes.fromhex(m['data_hex']) for m in writes)==(out/'upload.dat').read_bytes()
        reads=[m['ftp'] for m in ftp_down if m['ftp']['opcode']==128 and m['ftp']['request_opcode']==15]
        assert [m['offset'] for m in reads]==[0,110] and b''.join(bytes.fromhex(m['data_hex']) for m in reads)==(out/'download.dat').read_bytes()
        received=packed(out/'download.dat'); fields=['param1','param2','param3','param4','x','y','z','command','frame']
        assert all(all(a[f]==b[f] for f in fields) for a,b in zip(upload,received))
        assert [m['seq'] for m in received]==list(range(4)) and [m['mission_type'] for m in received]==[1]*4
        mission_items=[m for m in pick(down,'MISSION_ITEM_INT') if m['mission_type']==1 and m['source']==[1,1]]
        assert [m['seq'] for m in mission_items]==list(range(4))
        assert all(all(a[f]==b[f] for f in fields) for a,b in zip(received,mission_items))
        summary.update({'download':received,'mission_items':mission_items,'compared_fields':fields})
        summary['hashes']['download.dat']=sha(out/'download.dat')
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(case,'FTP uplink',len(ftp_up),'downlink',len(ftp_down))
