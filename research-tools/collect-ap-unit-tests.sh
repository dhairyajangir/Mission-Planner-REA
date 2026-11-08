#!/bin/bash
# Collect the ArduPilot unit-test results (non-debug SITL build) into the repository: per-test CSV with source library,
# trimmed check log, failure output, and configure summary.
D='/mnt/c/Users/think/OneDrive/Documents/ChatGPT/The Drone Project/mission-planner-rea-upload/ap-unit-tests-evidence'
mkdir -p "$D"
cd ~/ap-snapshot || exit 1
LOG=~/ap-tests-logs
echo "test,library,source,result" > "$D/ap-unit-tests.csv"
failed=$(sed -n '/tests failed/,$p' $LOG/check.log | grep 'build/sitl/tests/' | sed 's#.*/tests/##')
for f in build/sitl/tests/test_*; do
  [ -x "$f" ] || continue
  t=$(basename $f)
  src=$(find libraries -path "*/tests/$t.cpp" | head -1)
  lib=$(echo "$src" | cut -d/ -f2)
  res=pass
  echo "$failed" | grep -qx "$t" && res=FAIL
  echo "$t,$lib,$src,$res" >> "$D/ap-unit-tests.csv"
done
grep -E "returned|tests failed|check:" $LOG/check.log | sed 's#/home/think/ap-snapshot/##' > "$D/check-summary.txt"
cp -r $LOG/failures "$D/failures-nondebug"
grep -E "Debug build|Board|Checking for 'g\+\+'|Setting top|CXX |Optimisation|Coverage" $LOG/configure.log | head -12 > "$D/configure-summary.txt"
cat > "$D/NOTES.md" <<'EOF'
Built from a copy of `ardupilot-source/ardupilot-master` (pinned snapshot, commit 72b238201f5ea3b556e3809b2ec704fcf701474a)
without `modules/ChibiOS` and `modules/gsoap`, inside WSL Ubuntu 24.04 (g++ 13.3). The copy has no `.git`; the waf build calls git
for version headers, so a throwaway empty repository was created in the copy and any commit hash printed by the build is NOT the
pinned commit. First configure: `--board sitl` without `--debug`.
EOF
wc -l "$D/ap-unit-tests.csv"
awk -F, 'NR>1{c[$4]++} END{for(k in c) print k, c[k]}' "$D/ap-unit-tests.csv"
