#!/bin/bash
# Run the prototype's command line (python -m customgcs ...) against one disposable Copter simulator in WSL and record every command's output and exit code.
# usage: bash cli-smoke.sh <out dir>        Simulator only, never a real vehicle.
OUT="$1"
mkdir -p "$OUT"
source ~/venv-ap/bin/activate
rm -rf ~/custom-gcs && cp -r "$(dirname "$(readlink -f "$0")")/.." ~/custom-gcs
cd ~/custom-gcs
pkill -f build/sitl/bin/ardu; sleep 1
mkdir -p ~/cg-cli && cd ~/cg-cli && rm -rf ./*
~/ap-snapshot/build/sitl/bin/arducopter -w --model + -I 0 -s 1 --home -35.363261,149.165230,584,0 > sitl.log 2>&1 &
sleep 20
cd ~/custom-gcs
python3 - <<'EOF'
from customgcs import mission
items = [mission.Item(0, 0, 16, 0, 1, 0, 0, 0, 0, -35.363261, 149.16523, 584.0), mission.Item(1, 3, 22, 1, 1, 0, 0, 0, 0, 0.0, 0.0, 15.0),
         mission.Item(2, 3, 16, 0, 1, 0, 0, 0, 0, -35.3625, 149.166, 20.0), mission.Item(3, 3, 20, 0, 1, 0, 0, 0, 0, 0.0, 0.0, 0.0)]
open('plan.waypoints', 'w').write(mission.dumps_wpl(items))
open('bad.waypoints', 'w').write(mission.dumps_wpl(items).replace('-35.36250000', 'nan'))
EOF
run() {
  echo "\$ python -m customgcs $*" | tee -a "$OUT/cli-smoke.txt"
  python3 -m customgcs "$@" 2>&1 | tee -a "$OUT/cli-smoke.txt"
  echo "exit=${PIPESTATUS[0]}" | tee -a "$OUT/cli-smoke.txt"
  echo | tee -a "$OUT/cli-smoke.txt"
}
rm -f "$OUT/cli-smoke.txt"
run info
run modes
run params-save --file base.param
run params-diff --file base.param
sed -i 's/^RTL_ALT_M,.*/RTL_ALT_M,25/' base.param
run params-diff --file base.param
run params-restore --file base.param --dry-run
run params-restore --file base.param
run params-diff --file base.param
run mode --name LOITER
run mode --name FLIP
run arm
run params-restore --file base.param
run disarm
run mission-upload --file plan.waypoints
run mission-verify --file plan.waypoints
run mission-download --file down.waypoints
run mission-clear
run mission-upload --file bad.waypoints
run arm --host 10.1.2.3
cp base.param plan.waypoints down.waypoints "$OUT/" 2>/dev/null
pkill -f build/sitl/bin/ardu
