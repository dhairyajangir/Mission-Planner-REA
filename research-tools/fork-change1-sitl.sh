#!/bin/bash
# Build Copter SITL from the fork (branch "ours", after fork changes 1 and 2) and replay the NaN / infinity / valid float MISSION_ITEM
# test under gdb. Baseline (unpatched) result for comparison: sitl-evidence/nan-wp-gdb/ (NaN: SIGFPE in check_lat). Disposable simulator only.
source ~/venv-ap/bin/activate
REPO='/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload'
cd ~/ardupilot-fork || exit 1
echo "fork head: $(git log --oneline | head -1)"
python3 modules/waf/waf-light build --no-submodule-update --targets bin/arducopter -j4 > ~/fork-logs/build-copter.log 2>&1
echo "copter build exit=$?"
BIN=~/ardupilot-fork/build/sitl/bin/arducopter
ls -la $BIN | cut -c1-90
OUT=~/fork-sitl-nan; rm -rf $OUT; mkdir -p $OUT
for v in nan inf valid; do
  pkill -f 'build/sitl/bin/ardu' 2>/dev/null; sleep 1
  echo "=== variant $v"
  python3 "$REPO/research-tools/sitl-nan-wp-gdb.py" $BIN $OUT $v 2>&1 | tail -6
  grep -c SIGFPE $OUT/gdb-$v.log | sed 's/^/SIGFPE lines in gdb log: /'
done
mkdir -p "$REPO/sitl-evidence/fork-change1"
cp $OUT/gdb-*.log "$REPO/sitl-evidence/fork-change1/"
cp ~/fork-logs/result-*.txt ~/fork-logs/run-*.log "$REPO/sitl-evidence/fork-change1/" 2>/dev/null
cd ~/ardupilot-fork && git log --oneline | head -4 > "$REPO/sitl-evidence/fork-change1/fork-commits.txt"
echo done
