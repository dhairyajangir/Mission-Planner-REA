#!/bin/bash
# Stop a running autotest and its simulator cleanly (my own disposable test job) and record that it was stopped by hand.
# usage: stop-autotest.sh <vehicle> [tag]
VEH=$1; NAME=$VEH${2:+-$2}
pkill -TERM -f 'Tools/autotest/autotest.py'; sleep 3
pkill -TERM -f 'build/sitl/bin/ardu'; pkill -TERM -f 'build/sitl/bin/antennatracker'; pkill -TERM -f 'build/sitl/bin/blimp'; sleep 2
pkill -KILL -f 'Tools/autotest/autotest.py' 2>/dev/null
pkill -KILL -f 'build/sitl/bin/' 2>/dev/null
echo "stopped by hand at $(date)" >> ~/autotest-logs/$NAME.progress
echo "passed: $(grep -c '^AT-[0-9.]*: PASSED: "' ~/autotest-logs/$NAME.log)  failed: $(grep -c '^AT-[0-9.]*: FAILED: "' ~/autotest-logs/$NAME.log)"
pgrep -fa 'autotest.py|build/sitl/bin' | head -3 || true
