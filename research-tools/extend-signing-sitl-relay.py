from pathlib import Path
p=Path(__file__).resolve().parent.parent/'sitl-evidence/command-ack-relay.py'
s=p.read_text()
if "'signing_sitl'" not in s:
    s=s.replace("'fence_mavftp_pumped'", "'fence_mavftp_pumped', 'signing_sitl'",1)
    s=s.replace("result = {'scope': (", "result = {'scope': ('Disposable disarmed Copter SITL; synthetic MAVLink signing key' if case == 'signing_sitl' else\n                    ",1)
    p.write_text(s)
