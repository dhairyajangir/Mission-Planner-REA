from pathlib import Path
p = Path('sitl-evidence/command-ack-relay.py')
s = p.read_text(encoding='utf-8')
old = "if case not in ('guided_flight',"
assert s.count(old) == 1
s = s.replace(old, "if case not in ('guided_flight_retry', 'guided_flight',", 1)
s = s.replace("case == 'guided_flight'", "case in ('guided_flight', 'guided_flight_retry')")
p.write_text(s, encoding='utf-8')
