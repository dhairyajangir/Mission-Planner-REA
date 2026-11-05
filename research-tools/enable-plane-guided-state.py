from pathlib import Path
p = Path('sitl-evidence/command-ack-relay.py')
s = p.read_text(encoding='utf-8')
old = "if case not in ('plane_guided_drop_one',"
assert s.count(old) == 1
s = s.replace(old, "if case not in ('plane_guided_state', 'plane_guided_drop_one',", 1)
p.write_text(s, encoding='utf-8')
