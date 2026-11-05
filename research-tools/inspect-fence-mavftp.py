import os
from pathlib import Path
import struct
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root/'sitl-evidence/python'))
os.environ['MAVLINK20'] = '1'
from pymavlink.dialects.v20 import ardupilotmega
out = root/'sitl-evidence/command-ack-fence_mavftp_pumped'
for direction in ('to_sitl_output','to_client_output'):
    parser = ardupilotmega.MAVLink(None); parser.robust_parsing = True
    print(direction)
    for b in (out/(direction+'.bin')).read_bytes():
        msg = parser.parse_char(bytes([b]))
        if msg and msg.get_type() == 'FILE_TRANSFER_PROTOCOL':
            payload = bytes(msg.payload); header = struct.unpack('<HBBBBBBI',payload[:12]); print(header,repr(payload[12:12+header[3]][:32]))
for name in ('upload.dat','download.dat'):
    data = (out/name).read_bytes()
    print(name,'header',struct.unpack('<5H',data[:10]),'len',len(data))
