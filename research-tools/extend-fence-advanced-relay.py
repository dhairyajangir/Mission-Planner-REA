from pathlib import Path
p = Path(__file__).resolve().parent.parent / 'sitl-evidence/command-ack-relay.py'
s = p.read_text()
if "'fence_advanced_legacy'" not in s:
    s = s.replace("'fence_typed_legacy'", "'fence_typed_legacy', 'fence_advanced_legacy'")
    p.write_text(s)
