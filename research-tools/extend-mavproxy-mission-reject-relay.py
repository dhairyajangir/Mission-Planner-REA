from pathlib import Path
p=Path(__file__).resolve().parent.parent/'sitl-evidence/command-ack-relay.py'
s=p.read_text()
if "'mavproxy_mission_reject'" not in s:
    s=s.replace("'mavproxy_mission_normal_retry'", "'mavproxy_mission_reject', 'mavproxy_mission_normal_retry'",1)
    p.write_text(s)
