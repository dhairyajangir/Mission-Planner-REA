from pathlib import Path
p=Path(__file__).resolve().parent.parent/'sitl-evidence/command-ack-relay.py'
s=p.read_text()
if "'signing_discovery_match'" not in s:
    s=s.replace("'signing_sitl'", "'signing_sitl', 'signing_discovery_match', 'signing_discovery_missing'",1)
    s=s.replace("if case == 'signing_sitl' else", "if case in ('signing_sitl', 'signing_discovery_match', 'signing_discovery_missing') else",1)
    p.write_text(s)
