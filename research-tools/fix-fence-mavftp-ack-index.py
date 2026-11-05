from pathlib import Path
p=Path(__file__).resolve().parent.parent/'sitl-evidence/command-ack-relay.py'
s=p.read_text()
if "'fence_mavftp_last_ack_retry'" not in s:
    s=s.replace("'fence_mavftp_last_ack_fixed'", "'fence_mavftp_last_ack_fixed', 'fence_mavftp_last_ack_retry'")
    s=s.replace('request_opcode = payload[7]', 'request_opcode = payload[8]')
    p.write_text(s)
