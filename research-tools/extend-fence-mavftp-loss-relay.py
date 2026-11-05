from pathlib import Path
p=Path(__file__).resolve().parent.parent/'sitl-evidence/command-ack-relay.py'
s=p.read_text()
if "'fence_mavftp_partial'" not in s:
    s=s.replace("'fence_mavftp_drop_writes'", "'fence_mavftp_drop_writes', 'fence_mavftp_partial', 'fence_mavftp_last_ack'",1)
    needle="        if case == 'terrain_drop_one' and direction == 'to_sitl' and msgid == 134:\n"
    addition='''        if case in ('fence_mavftp_partial', 'fence_mavftp_last_ack') and msgid == 110 and len(payload) >= 15:
            opcode = payload[6]
            request_opcode = payload[7]
            offset = int.from_bytes(payload[11:15], 'little')
            drop_write = case == 'fence_mavftp_partial' and direction == 'to_sitl' and opcode == 7 and offset >= 80
            drop_ack = case == 'fence_mavftp_last_ack' and direction == 'to_client' and opcode == 128 and request_opcode == 7 and offset == 160
            if drop_write or drop_ack:
                files['dropped'].write(packet)
                result['dropped_ftp_packets'] = result.get('dropped_ftp_packets', 0) + 1
                continue
'''
    assert s.count(needle)==1
    s=s.replace(needle,addition+needle)
    s=s.replace("result = {'scope': ('Disposable Copter SITL; drop all MAVFTP write requests'", "result = {'scope': ('Disposable Copter SITL; simulated partial MAVFTP write or acknowledgment loss' if case in ('fence_mavftp_partial', 'fence_mavftp_last_ack') else\n                    'Disposable Copter SITL; drop all MAVFTP write requests'")
    p.write_text(s)
