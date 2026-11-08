#!/bin/bash
# Show the exception text of a failed autotest: lines from "Exception caught" to the end of the traceback.
# usage: show-autotest-failure.sh <log name in ~/autotest-logs> [number of failures to show]
f=~/autotest-logs/$1
n=${2:-5}
grep -n 'Exception caught' "$f" | head -$n | cut -c1-220 | while IFS=: read -r ln rest; do
  echo "=== line $ln: $rest"
  sed -n "$((ln+1)),$((ln+22))p" "$f" | grep -v '^$' | cut -c1-200 | tail -9
done
