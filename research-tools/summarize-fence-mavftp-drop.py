"""Validate dropped MAVFTP writes against a previously uploaded fence."""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
root=Path(__file__).resolve().parent.parent
out=root/'sitl-evidence/command-ack-fence_mavftp_drop_writes'
sys.path.insert(0,str(root/'sitl-evidence/python'))
os.environ['MAVLINK20']='1'
from pymavlink.dialects.v20 import ardupilotmega
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
relay=json.loads((out/'relay-result.json').read_text())
assert relay['case']=='fence_mavftp_drop_writes' and not relay['errors'] and relay['closed_by']=='client' and relay['buffered_bytes_at_close']==0
assert relay['binary_sha256']==sha(root/'sitl-evidence/archive-built/arducopter')
assert all(sha(out/name)==digest for name,digest in relay['capture_sha256'].items())
def decode(path):
    parser=ardupilotmega.MAVLink(None);parser.robust_parsing=True;found=[];bad=0
    for b in path.read_bytes():
        m=parser.parse_char(bytes([b]))
        if m is None: continue
        if m.get_type()=='BAD_DATA':bad+=1;continue
        d=m.to_dict();d['source']=[m.get_srcSystem(),m.get_srcComponent()]
        if m.get_type()=='FILE_TRANSFER_PROTOCOL':
            payload=bytes(m.payload);h=struct.unpack('<HBBBBBBI',payload[:12])
            d['ftp']={'seq':h[0],'session':h[1],'opcode':h[2],'size':h[3],'request_opcode':h[4],'offset':h[7], 'data_hex':payload[12:12+h[3]].hex()}
        found.append(d)
    return found,bad
pick=lambda rows,kind:[m for m in rows if m['mavpackettype']==kind]
up,bad_up=decode(out/'to_sitl_input.bin');delivered,bad_delivered=decode(out/'to_sitl_output.bin')
down,bad_down=decode(out/'to_client_output.bin');dropped,bad_dropped=decode(out/'dropped.bin')
ftp_in=pick(up,'FILE_TRANSFER_PROTOCOL');ftp_out=pick(delivered,'FILE_TRANSFER_PROTOCOL');ftp_down=pick(down,'FILE_TRANSFER_PROTOCOL')
writes=[m for m in ftp_in if m['ftp']['opcode']==7]
assert len(writes)==len(dropped)==relay['dropped_ftp_writes']==30 and bad_dropped==0
assert all(m['mavpackettype']=='FILE_TRANSFER_PROTOCOL' and m['ftp']['opcode']==7 and m['ftp']['offset']==0 for m in dropped)
assert writes == dropped
assert not any(m['ftp']['opcode']==7 for m in ftp_out)
assert any(m['ftp']['opcode']==6 and bytes.fromhex(m['ftp']['data_hex'])==b'@MISSION/fence.dat' for m in ftp_out)
assert any(m['ftp']['opcode']==128 and m['ftp']['request_opcode']==6 for m in ftp_down)
baseline=[m for m in pick(up,'MISSION_ITEM_INT') if m['mission_type']==1]
readback=[m for m in pick(down,'MISSION_ITEM_INT') if m['mission_type']==1 and m['source']==[1,1]]
assert max(i for i,m in enumerate(up) if m in baseline) < min(i for i,m in enumerate(up) if m in ftp_in)
assert any(m['mavpackettype']=='MISSION_ACK' and m['mission_type']==1 and m['type']==0 and m['source']==[1,1] for m in down)
assert [m['seq'] for m in baseline]==list(range(4))==[m['seq'] for m in readback]
assert [m['command'] for m in baseline]==[5001,5001,5001,5004] and [m['param1'] for m in baseline]==[3,3,3,15]
fields=['seq','command','param1','param2','param3','param4','x','y','z','mission_type']
assert all(all(a[f]==b[f] for f in fields) for a,b in zip(baseline,readback))
packed=(out/'upload.dat').read_bytes();assert struct.unpack('<5H',packed[:10])==(0x763d,1,0,0,4)
replacement=[struct.unpack('<ffffiifHHBBBBBB',packed[10+i*38:48+i*38]) for i in range(4)]
assert [r[0] for r in replacement]==[3,3,3,25] and [r[8] for r in replacement]==[5001,5001,5001,5004]
assert replacement[3][0]!=readback[3]['param1']
heartbeats=[m for m in pick(down,'HEARTBEAT') if m['source']==[1,1]]
assert heartbeats and all(not(m['base_mode'] & 128) for m in heartbeats)
log=(out/'probe.log').read_text(encoding='utf8',errors='replace')
assert (out/'probe-exit.txt').read_text().strip()=='0'
assert all(s in log for s in ['FTP_UPLOAD_RETURNED=True BYTES=162','MISSION_COUNT=4','DROP_PROBE_COMPLETE=True'])
summary={'scope':'One disarmed source-built Copter 4.8-dev run; relay dropped every MAVFTP write request',
         'relay':relay,'baseline':baseline,'readback':readback,'compared_fields':fields,'ftp_input':ftp_in,'ftp_delivered':ftp_out,
         'ftp_responses':ftp_down,'dropped':dropped,'replacement_last_radius':replacement[3][0],'heartbeats':heartbeats,
         'bad_data_fragments':{'uplink':bad_up,'delivered':bad_delivered,'downlink':bad_down,'dropped':bad_dropped},
         'hashes':{n:sha(out/n) for n in ['probe-source.cs','probe.exe','probe.log','probe-exit.txt','upload.dat']},
         'library_hashes':{n:sha(root/'mission-planner-portable'/n) for n in
              ['MissionPlanner.ArduPilot.dll','MissionPlanner.Utilities.dll','MissionPlanner.Comms.dll','MAVLink.dll','Interfaces.dll','System.ValueTuple.dll','FenceMavftpDropProbe.exe.config']}}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print('Dropped',len(dropped),'writes; baseline and readback items',len(readback))
