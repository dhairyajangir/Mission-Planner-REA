import os,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(root/'sitl-evidence/python'));os.environ['MAVLINK20']='1'
from pymavlink.dialects.v20 import ardupilotmega
for case in ('default','disabled','disarmed'):
    out=root/'sitl-evidence'/('command-ack-mavproxy_forward_'+case);print(case)
    for name in ('request.bin','to_sitl_output.bin','udp-after.bin'):
        parser=ardupilotmega.MAVLink(None);parser.robust_parsing=True;rows=[]
        for b in (out/name).read_bytes():
            m=parser.parse_char(bytes([b]))
            if m and m.get_type() in ('PARAM_REQUEST_READ','PARAM_VALUE'):
                if getattr(m,'param_id','')=='LOG_DISARMED':rows.append((m.get_type(),m.get_srcSystem(),m.get_srcComponent(),m.to_dict()))
        print(name,rows)
