#!/bin/bash
# Run MP's bundled LogAnalyzer (copy in ~/la) under Python 3 after four mechanical Python 2 -> 3 edits, on a SITL log.
# Usage: run-loganalyzer-py3.sh <log file> <output xml>
cd ~/la || exit 1
sed -i 's/except Exception, e:/except Exception as e:/' LogAnalyzer.py
sed -i 's/\.iteritems()/.items()/' DataflashLog.py tests/TestParams.py tests/TestPitchRollCoupling.py
diff <(cd ~ && echo) /dev/null >/dev/null
~/venv-ap/bin/python LogAnalyzer.py "$1" -x "$2" 2>&1 | tail -40
echo "exit=$?"
ls -l "$2" 2>/dev/null
