from pathlib import Path
p = Path('sitl-evidence/command-ack-relay.py')
s = p.read_text(encoding='utf-8')
old = "if case not in ('plane_guided_state',"
assert s.count(old) == 1
s = s.replace(old, "if case not in ('wpl_nan_int', 'wpl_nan_float', 'plane_guided_state',", 1)
old = "result = {'scope': ("
assert s.count(old) == 1
s = s.replace(old, old + "'Disposable Copter SITL; synthetic nonfinite waypoint upload' if case.startswith('wpl_nan_') else ", 1)
p.write_text(s, encoding='utf-8')
