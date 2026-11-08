#!/bin/bash
# Re-run the patched LogAnalyzer copy on the converted SITL log and store console output and XML in the repository.
cd ~/la || exit 1
D='/mnt/c/Users/think/OneDrive/Documents/ChatGPT/The Drone Project/mission-planner-rea-upload/sitl-evidence/loganalyzer-run'
mkdir -p "$D"
~/venv-ap/bin/python LogAnalyzer.py copter-flight.log -x out.xml -s > console.txt 2>&1
cp console.txt "$D/console.txt"
cp out.xml "$D/analysis.xml"
sha256sum copter-flight.BIN | cut -c1-64 > "$D/input-bin-sha256.txt"
cat > "$D/EDITS.md" <<'EOF'
Edits made to a scratch copy of `mission-planner-1.3.83-source/LogAnalyzer/py2exe` (the repository copy is unchanged):

- `LogAnalyzer.py`: `except Exception, e:` -> `except Exception as e:`
- `DataflashLog.py`, `tests/TestParams.py`, `tests/TestPitchRollCoupling.py`: `.iteritems()` -> `.items()`
- `imp.py` added: `research-tools/imp_shim.py` (Python 3.12 has no `imp` module)
- Input: the binary log written by the Copter SITL flight in `sitl-evidence/copter-air-modes/`, converted to text by
  `research-tools/bin_to_text_log.py` (the tool reads text logs only); run with `-s` (skip malformed lines; 11 were skipped).
EOF
grep -c . "$D/console.txt"
