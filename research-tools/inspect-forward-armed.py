import os,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(root/'sitl-evidence/python'));os.environ['MAVLINK20']='1'
from pymavlink.dialects.v20 import ardupilotmega
for mode in ('block_retry','allow_retry'):
    out=root/'sitl-evidence'/('command-ack-mavproxy_forward_armed_'+mode);print(mode)
    for name in ('control-uplink.bin','control-downlink.bin','udp-armed-before.bin','udp-after.bin','to_sitl_output.bin'):
        p=ardupilotmega.MAVLink(None);p.robust_parsing=True;rows=[]
        for b in (out/name).read_bytes():
            m=p.parse_char(bytes([b]))
            if m is None:continue
            t=m.get_type()
            if t=='COMMAND_LONG' and m.command==400:rows.append((t,m.to_dict()))
            if t=='COMMAND_ACK' and m.command==400:rows.append((t,m.to_dict()))
            if t=='HEARTBEAT' and m.get_srcSystem()==1:rows.append((t,m.base_mode))
            if t in ('PARAM_REQUEST_READ','PARAM_VALUE') and getattr(m,'param_id',None)=='LOG_DISARMED':rows.append((t,m.get_srcSystem(),m.to_dict()))
        print(name,rows[-12:])
