#!/bin/bash
# Run the prototype's motor test (python -m customgcs motor-test) against disposable simulators in Ubuntu-E and record each outcome in evidence/.
# usage: bash run-integration.sh   (copies custom-gcs to ~/custom-gcs, starts each simulator on tcp 5760, runs, stops). Simulator only, never a real vehicle.
REPO='/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload'
OUT="$REPO/sitl-evidence/custom-gcs-integration"
mkdir -p "$OUT"
source ~/venv-ap/bin/activate
rm -rf ~/custom-gcs && cp -r "$REPO/custom-gcs" ~/custom-gcs
cd ~/custom-gcs
run() {   # label binary model [extra args]
  label=$1; bin=$2; model=$3; shift 3
  pkill -f build/sitl/bin/ardu; sleep 1
  mkdir -p ~/cg-work/$label && cd ~/cg-work/$label && rm -rf ./*
  ~/ap-snapshot/build/sitl/bin/$bin -w --model $model -I 0 -s 1 --home -35.363261,149.165230,584,0 > sitl.log 2>&1 &
  sleep 14
  cd ~/custom-gcs
  { echo "== $label ($bin --model $model)"; python3 -m customgcs motor-test --port 5760 "$@"; echo "exit=$?"; } 2>&1 | tee "$OUT/$label.txt"
  pkill -f build/sitl/bin/ardu; sleep 1
}
run copter-quad-plus arducopter +
run copter-hexa-x arducopter hexax
run copter-octa arducopter octa
run copter-y6 arducopter y6
run copter-tri arducopter tri
run quadplane arduplane quadplane
run quadplane-tri arduplane quadplane-tri
run sub-vectored ardusub vectored --arm
run rover-skid ardurover rover-skid
run rover-sailboat ardurover sailboat
