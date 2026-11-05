import collections,hashlib,os,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(root/'sitl-evidence/python'));os.environ['MAVLINK20']='1'
from pymavlink.dialects.v20 import ardupilotmega
key=bytes(range(32));out=root/'sitl-evidence/command-ack-signing_sitl'
for name in ('to_sitl_output.bin','to_client_output.bin'):
    parser=ardupilotmega.MAVLink(None);parser.robust_parsing=True;counts=collections.Counter(); signed=[]
    for b in (out/name).read_bytes():
        m=parser.parse_char(bytes([b]))
        if m is None or m.get_type()=='BAD_DATA':continue
        raw=bytes(m.get_msgbuf());sig=raw[0]==253 and raw[2]&1
        counts[(m.get_type(),bool(sig))]+=1
        if sig:
            valid=hashlib.sha256(key+raw[:-6]).digest()[:6]==raw[-6:]
            valid_zero=hashlib.sha256(bytes(32)+raw[:-6]).digest()[:6]==raw[-6:]
            signed.append((m.get_type(),valid,valid_zero,raw[-13],int.from_bytes(raw[-12:-6],'little')))
    print(name,counts, 'signed',signed[:20])
