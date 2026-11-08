#!/bin/bash
# Run ArduPilot's own autotest suite for one vehicle against the pinned-snapshot copy in WSL (~/ap-snapshot).
# usage: [STEPS="build.X test.X.Name"] [SPEEDUP=10] [TAG=name] run-autotest.sh <vehicle e.g. Blimp> [extra autotest args]
# Disposable simulator only. Output: ~/autotest-logs/<vehicle>[-TAG].log
VEH=$1; shift
STEPS=${STEPS:-"build.$VEH test.$VEH"}
SPEEDUP=${SPEEDUP:-10}
NAME=$VEH${TAG:+-$TAG}
cd ~/ap-snapshot || exit 1
source ~/venv-ap/bin/activate
mkdir -p ~/autotest-logs
echo "start $(date) steps=$STEPS speedup=$SPEEDUP" > ~/autotest-logs/$NAME.progress
python3 Tools/autotest/autotest.py --no-clean --no-check-parameter-leaks --waf-configure-args=--no-submodule-update --speedup=$SPEEDUP "$@" $STEPS > ~/autotest-logs/$NAME.log 2>&1
echo "exit=$? $(date)" >> ~/autotest-logs/$NAME.progress
