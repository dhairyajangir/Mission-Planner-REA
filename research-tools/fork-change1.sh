#!/bin/bash
# Fork change 1 (branch "ours" in ~/ardupilot-fork): make check_lat/check_lng(float) safe for NaN/infinity.
# usage: fork-change1.sh red     add the unit test only, build it and run it on the unpatched code (expected to die with SIGFPE)
#        fork-change1.sh green   apply the fix, rebuild and run the test (expected to pass)
# Logs go to ~/fork-logs. Disposable simulator/unit-test build only.
set -u
STAGE=$1
REPO='/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload'
F=~/ardupilot-fork
LOG=~/fork-logs; mkdir -p $LOG
source ~/venv-ap/bin/activate
cd $F || exit 1
git config user.name "ardupilot-rea fork"; git config user.email "fork@localhost"

build_and_run() {
  local tag=$1
  [ -f build/sitl/c4che/_cache.py ] || python3 modules/waf/waf-light configure --board sitl --no-submodule-update > $LOG/configure-$tag.log 2>&1
  python3 modules/waf/waf-light build --no-submodule-update --targets tests/test_check_latlng -j4 > $LOG/build-$tag.log 2>&1
  echo "build exit=$?" | tee -a $LOG/result-$tag.txt
  ./build/sitl/tests/test_check_latlng > $LOG/run-$tag.log 2>&1
  echo "test exit=$? (139 = SIGSEGV, 136 = SIGFPE)" | tee -a $LOG/result-$tag.txt
  tail -n 12 $LOG/run-$tag.log
}

case $STAGE in
  red)
    # start from the baseline plus nothing else, so the test commit is the only difference
    git reset -q --hard baseline-72b23820
    cp "$REPO/research-tools/fork-change1-test.cpp" libraries/AP_Math/tests/test_check_latlng.cpp
    git add libraries/AP_Math/tests/test_check_latlng.cpp
    git commit -q -m "test: check_lat/check_lng must reject NaN and infinity and be exact at the integer limits

Without the fix the NaN case dies with SIGFPE (SITL enables FE_INVALID) and the integer limit case accepts one unit past the limit."
    rm -f $LOG/result-red.txt
    build_and_run red
    ;;
  green)
    python3 - <<'EOF'
import re
p = 'libraries/AP_Math/location.cpp'
s = open(p).read()
old_lat = "bool check_lat(float lat)\n{\n    return fabsf(lat) <= 90;\n}"
old_lng = "bool check_lng(float lng)\n{\n    return fabsf(lng) <= 180;\n}"
assert old_lat in s and old_lng in s
s = s.replace(old_lat, "bool check_lat(float lat)\n{\n    // isfinite() first: an ordered comparison with NaN raises FE_INVALID, which SITL turns into SIGFPE\n    return isfinite(lat) && fabsf(lat) <= 90;\n}")
s = s.replace(old_lng, "bool check_lng(float lng)\n{\n    return isfinite(lng) && fabsf(lng) <= 180;\n}")
open(p, 'w').write(s)
EOF
    git add libraries/AP_Math/location.cpp
    git commit -q -m "AP_Math: check_lat/check_lng(float) reject non-finite input before comparing

An ordered comparison with NaN raises FE_INVALID; SITL enables that trap, so a MISSION_ITEM with NaN latitude killed the simulator with SIGFPE." || true
    rm -f $LOG/result-green.txt
    build_and_run green
    ;;
  green2)
    python3 - <<'EOF'
p = 'libraries/AP_Math/location.cpp'
s = open(p).read()
old_lat = "bool check_lat(int32_t lat)\n{\n    return labs(lat) <= 90*1e7;\n}"
old_lng = "bool check_lng(int32_t lng)\n{\n    return labs(lng) <= 180*1e7;\n}"
assert old_lat in s and old_lng in s
s = s.replace(old_lat, "bool check_lat(int32_t lat)\n{\n    // integer limit: 90*1e7 is a float constant under -fsingle-precision-constant and the comparison would round\n    return labs(lat) <= 900000000L;\n}")
s = s.replace(old_lng, "bool check_lng(int32_t lng)\n{\n    return labs(lng) <= 1800000000L;\n}")
open(p, 'w').write(s)
EOF
    git add libraries/AP_Math/location.cpp
    git commit -q -m "AP_Math: check_lat/check_lng(int32_t) compare against exact integer limits

90*1e7 is a float constant when built with -fsingle-precision-constant, so a value one unit past the limit rounded onto it and was accepted." || true
    rm -f $LOG/result-green2.txt
    build_and_run green2
    ;;
esac
git log --oneline | head -3
