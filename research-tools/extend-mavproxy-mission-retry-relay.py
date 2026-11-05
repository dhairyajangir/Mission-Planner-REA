from pathlib import Path
p=Path(__file__).resolve().parent.parent/'sitl-evidence/command-ack-relay.py'
s=p.read_text()
if "'mavproxy_mission_normal_retry'" not in s:
    s=s.replace("'mavproxy_mission_normal', 'mavproxy_mission_drop_ack'", "'mavproxy_mission_normal', 'mavproxy_mission_drop_ack', 'mavproxy_mission_normal_retry', 'mavproxy_mission_drop_ack_retry'",1)
    s=s.replace("if case == 'mavproxy_mission_drop_ack' and", "if case in ('mavproxy_mission_drop_ack','mavproxy_mission_drop_ack_retry') and",1)
    p.write_text(s)
