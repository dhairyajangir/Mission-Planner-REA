from pathlib import Path
p = Path('sitl-evidence/command-ack-relay.py')
s = p.read_text(encoding='utf-8')
old = "if case not in ('guided_flight_retry',"
assert s.count(old) == 1
s = s.replace(old, "if case not in ('plane_guided', 'guided_flight_retry',", 1)
old = "binary = base / ('arducopter'"
assert s.count(old) == 1
s = s.replace(old, "binary = base / ('archive-built-variants/arduplane' if case == 'plane_guided' else 'arducopter'", 1)
old = "result = {'scope': ("
assert s.count(old) == 1
s = s.replace(old, old + "'Disposable disarmed Plane SITL; guided mission-item test' if case == 'plane_guided' else ", 1)
old = "'--model', 'calibration' if case == 'calibration_full' else 'quad'"
assert s.count(old) == 1
s = s.replace(old, "'--model', 'plane' if case == 'plane_guided' else 'calibration' if case == 'calibration_full' else 'quad'", 1)
p.write_text(s, encoding='utf-8')
