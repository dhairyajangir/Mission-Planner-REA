#!/bin/bash
LOG=~/ap-tests-logs
grep -n "Debug build" $LOG/configure-debug.log
grep -c "HAL_DEBUG_BUILD" ~/ap-snapshot/build/sitl/c4che/_cache.py 2>/dev/null
grep -o "HAL_DEBUG_BUILD[^ ,']*" ~/ap-snapshot/build/sitl/c4che/_cache.py | sort | uniq -c | head
grep -n -B1 -A6 "Failure" $LOG/debug-run/test_math_double.txt | head -14
grep -n "Error msg" -A3 $LOG/debug-run/test_bitmask.txt | head -8
tail -5 $LOG/build-debug.log | cut -c1-160
grep -rn "HAL_DEBUG_BUILD" ~/ap-snapshot/Tools/ardupilotwaf/*.py ~/ap-snapshot/wscript | head -5
