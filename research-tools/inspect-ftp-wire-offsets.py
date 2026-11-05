import os,sys
from pathlib import Path
r=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(r/'sitl-evidence/python'));os.environ['MAVLINK20']='1'
from pymavlink.dialects.v20 import ardupilotmega
p=r/'sitl-evidence/command-ack-fence_mavftp_last_ack_fixed/to_client_input.bin'
parser=ardupilotmega.MAVLink(None);parser.robust_parsing=True
for b in p.read_bytes():
    m=parser.parse_char(bytes([b]))
    if m and m.get_type()=='FILE_TRANSFER_PROTOCOL':
        data=bytes(m.payload);offset=int.from_bytes(data[8:12],'little')
        if data[3]==128 and data[5]==7 and offset==160:
            raw=m.get_msgbuf();h=10 if raw[0]==253 else 6
            print('rawlength',raw[1],'payload bytes',bytes(raw[h:h+raw[1]]).hex(),'logical',data[:12].hex());break
