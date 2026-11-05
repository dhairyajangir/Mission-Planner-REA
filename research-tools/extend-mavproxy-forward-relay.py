from pathlib import Path
p=Path(__file__).resolve().parent.parent/'sitl-evidence/command-ack-relay.py'
s=p.read_text()
if "'mavproxy_forward_default'" not in s:
    s=s.replace("'mavproxy_mission_reject'", "'mavproxy_forward_default', 'mavproxy_forward_disabled', 'mavproxy_forward_disarmed', 'mavproxy_mission_reject'",1)
    s=s.replace("result = {'scope': (", "result = {'scope': ('Disposable Copter SITL; MAVProxy downstream read-only request forwarding' if case.startswith('mavproxy_forward_') else\n                    ",1)
    p.write_text(s)
