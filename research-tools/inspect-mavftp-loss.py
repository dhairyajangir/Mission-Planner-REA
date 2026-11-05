import os
from pathlib import Path
import struct
import sys
r=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(r/'sitl-evidence/python'));os.environ['MAVLINK20']='1'
from pymavlink.dialects.v20 import ardupilotmega
for case in ('fence_mavftp_partial','fence_mavftp_last_ack'):
    p=r/'sitl-evidence'/('command-ack-'+case); print(case)
    for name in ('to_sitl_input.bin','to_sitl_output.bin','to_client_input.bin','to_client_output.bin','dropped.bin'):
        parser=ardupilotmega.MAVLink(None);parser.robust_parsing=True;found=[]
        for b in (p/name).read_bytes():
            m=parser.parse_char(bytes([b]))
            if m and m.get_type()=='FILE_TRANSFER_PROTOCOL':
                h=struct.unpack('<HBBBBBBI',bytes(m.payload)[:12]);found.append((h[0],h[2],h[4],h[7]))
        print(name,found)
