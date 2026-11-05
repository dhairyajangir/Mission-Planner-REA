from pathlib import Path
path = Path(__file__).resolve().parent.parent / 'sitl-evidence/command-ack-relay.py'
source = path.read_text()
source = source.replace("if case == 'fence_typed_legacy':\n    case = 'fence_legacy_interop2'\n", '')
if "'fence_typed_legacy'" not in source:
    source = source.replace("'fence_legacy_interop'", "'fence_legacy_interop', 'fence_typed_legacy'")
path.write_text(source)
