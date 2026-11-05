from pathlib import Path
p = Path('sitl-evidence/command-ack-relay.py')
s = p.read_text(encoding='utf-8')
old = "if case not in ('normal',"
assert s.count(old) == 1
s = s.replace(old, "if case not in ('guided_position', 'normal',", 1)
old = "result = {'scope': ("
assert s.count(old) == 1
s = s.replace(old, old + "'Disposable disarmed Copter SITL; guided position packet test' if case == 'guided_position' else ", 1)
p.write_text(s, encoding='utf-8')
