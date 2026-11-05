from pathlib import Path
p=Path(__file__).resolve().parent.parent/'sitl-evidence/command-ack-relay.py'
s=p.read_text()
if "'fence_mavftp_last_ack_fixed'" not in s:
    s=s.replace("'fence_mavftp_partial', 'fence_mavftp_last_ack'", "'fence_mavftp_partial', 'fence_mavftp_last_ack', 'fence_mavftp_last_ack_fixed'")
    s=s.replace("and msgid == 110 and len(payload) >= 15:\n            opcode = payload[6]", "and msgid == 110 and len(payload) >= 8:\n            payload = payload.ljust(15, b'\\0')\n            opcode = payload[6]")
    s=s.replace("drop_ack = case == 'fence_mavftp_last_ack'", "drop_ack = case in ('fence_mavftp_last_ack', 'fence_mavftp_last_ack_fixed')")
    p.write_text(s)
