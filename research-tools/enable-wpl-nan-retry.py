from pathlib import Path
p = Path('sitl-evidence/command-ack-relay.py')
s = p.read_text(encoding='utf-8')
old = "if case not in ('wpl_nan_int',"
assert s.count(old) == 1
s = s.replace(old, "if case not in ('wpl_nan_float_retry', 'wpl_nan_int',", 1)
p.write_text(s, encoding='utf-8')
