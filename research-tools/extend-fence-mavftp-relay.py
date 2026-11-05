from pathlib import Path
p = Path(__file__).resolve().parent.parent/'sitl-evidence/command-ack-relay.py'
s = p.read_text()
if "'fence_mavftp'" not in s:
    s = s.replace("'fence_highlevel'", "'fence_highlevel', 'fence_mavftp'")
if "'fence_mavftp_pumped'" not in s:
    s = s.replace("'fence_mavftp'", "'fence_mavftp', 'fence_mavftp_pumped'")
p.write_text(s)
