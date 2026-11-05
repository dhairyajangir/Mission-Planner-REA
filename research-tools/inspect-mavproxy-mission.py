import os,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(root/'sitl-evidence/python'));os.environ['MAVLINK20']='1'
from pymavlink.dialects.v20 import ardupilotmega
for case in ('mavproxy_mission_normal_retry','mavproxy_mission_drop_ack_retry'):
    p=root/'sitl-evidence'/('command-ack-'+case);print(case)
    for name in ('to_sitl_output.bin','to_client_input.bin','to_client_output.bin','dropped.bin','independent-downlink.bin'):
        parser=ardupilotmega.MAVLink(None);parser.robust_parsing=True;msgs=[]
        for b in (p/name).read_bytes():
            m=parser.parse_char(bytes([b]))
            if m and m.get_type() in ('MISSION_COUNT','MISSION_ITEM','MISSION_ITEM_INT','MISSION_ACK','MISSION_REQUEST','MISSION_REQUEST_INT'):
                msgs.append((m.get_type(),m.to_dict()))
        print(name,msgs)
