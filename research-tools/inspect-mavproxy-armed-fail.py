import os,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(root/'sitl-evidence/python'));os.environ['MAVLINK20']='1'
from pymavlink.dialects.v20 import ardupilotmega
for mode in ('block','allow'):
    out=root/'sitl-evidence'/('command-ack-mavproxy_forward_armed_'+mode);p=ardupilotmega.MAVLink(None);p.robust_parsing=True;rows=[]
    for b in (out/'control-downlink.bin').read_bytes():
        m=p.parse_char(bytes([b]))
        if m and m.get_type() in ('STATUSTEXT','COMMAND_ACK'):rows.append((m.get_type(),m.to_dict()))
    print(mode,rows)
