#!/bin/bash
# Run the tests listed in ~/autotest-logs/<vehicle>-remaining.txt (made by autotest-remaining.sh) as individual autotest steps,
# with a longer overall timeout than the 90 minute default. Disposable simulator only.
# usage: run-autotest-remaining.sh <vehicle> <tag> [timeout seconds]
VEH=$1; TAG=$2; TMO=${3:-20000}
export STEPS=$(sed "s/^/test.$VEH./" ~/autotest-logs/$VEH-remaining.txt | tr '\n' ' ')
export SPEEDUP=8
export TAG
exec bash "$(dirname "$0")/run-autotest.sh" "$VEH" --timeout=$TMO
