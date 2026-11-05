from pathlib import Path
p = Path('sitl-evidence/command-ack-relay.py')
s = p.read_text(encoding='utf-8')
old = "if case not in ('guided_position',"
assert s.count(old) == 1
s = s.replace(old, "if case not in ('guided_flight', 'guided_position',", 1)
old = "result = {'scope': ('Disposable disarmed Copter SITL; guided position packet test'"
assert s.count(old) == 1
s = s.replace(old, "result = {'scope': ('Disposable Copter SITL; guided flight target test' if case == 'guided_flight' else 'Disposable disarmed Copter SITL; guided position packet test'", 1)
old = 'deadline = time.monotonic() + 120'
assert s.count(old) == 1
s = s.replace(old, "deadline = time.monotonic() + (240 if case == 'guided_flight' else 120)", 1)
p.write_text(s, encoding='utf-8')
