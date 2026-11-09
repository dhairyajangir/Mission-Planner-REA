#!/bin/bash
# Build and run ArduPilot's own C++ unit tests (waf "tests" target, board linux) in the pinned snapshot copy in WSL, one result line per test binary.
# Output: ~/unit-tests/{configure.log,build.log,results.csv,<binary>.log}. The linux board build goes to build/linux, separate from the SITL build used by the autotests.
# usage: run-unit-tests.sh
source ~/venv-ap/bin/activate
cd ~/ap-snapshot || exit 1
mkdir -p ~/unit-tests
echo "start $(date)" > ~/unit-tests/progress.txt
./waf configure --board linux --no-submodule-update > ~/unit-tests/configure.log 2>&1
echo "configure exit=$? $(date)" >> ~/unit-tests/progress.txt
./waf tests -j6 > ~/unit-tests/build.log 2>&1
echo "build exit=$? $(date)" >> ~/unit-tests/progress.txt
echo "binary,exit_code,seconds" > ~/unit-tests/results.csv
for t in build/linux/tests/*; do
  [ -f "$t" ] && [ -x "$t" ] || continue
  n=$(basename "$t")
  s=$(date +%s)
  timeout 300 "$t" > ~/unit-tests/$n.log 2>&1
  c=$?
  echo "$n,$c,$(( $(date +%s) - s ))" >> ~/unit-tests/results.csv
done
echo "tests done $(date)" >> ~/unit-tests/progress.txt
