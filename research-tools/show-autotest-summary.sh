#!/bin/bash
# Print PASSED/FAILED test lines and the last test started for an autotest log in ~/autotest-logs.
# usage: show-autotest-summary.sh <log name without path, e.g. Rover.log>
f=~/autotest-logs/$1
grep -E '^AT-[0-9.]+: (PASSED|FAILED): "' "$f" | sed -E 's/^AT-[0-9.]+: //' | cut -c1-120
echo "--- passed: $(grep -c '^AT-[0-9.]*: PASSED: "' "$f")  failed: $(grep -c '^AT-[0-9.]*: FAILED: "' "$f")"
echo "--- last test headers:"
grep -E '^AT-[0-9.]+: \.\.\.|^AT-[0-9.]+: .*>>>>' "$f" | tail -3 | cut -c1-160
grep -E 'Exception|Traceback' "$f" | tail -3 | cut -c1-160
