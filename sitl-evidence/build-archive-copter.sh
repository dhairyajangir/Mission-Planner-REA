#!/bin/sh
set -eu
base="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
source="$base/../ardupilot-source/ardupilot-master"
cd "$source"
export PYTHONPATH="$base/python${PYTHONPATH:+:$PYTHONPATH}"
number=1
while [ -e "$base/archive-copter-build-$number.log" ]; do
    number=$((number + 1))
done
log="$base/archive-copter-build-$number.log"
printf '%s\n' "$log" > "$base/archive-copter-last-log.txt"
python3 waf copter -j 2 > "$log" 2>&1
