#!/bin/bash
# After PageFrameProbe changed FRAME_CLASS/FRAME_TYPE in ~/fp-change: start the simulator again WITHOUT wiping parameters and motor-test it.
REPO='/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload'
DEST="$REPO/sitl-evidence/frame-page/restart-sweep"
source ~/venv-ap/bin/activate
cp "$REPO/research-tools/sitl-frame-motor-sweep.py" ~/sitl-frame-motor-sweep.py
rm -rf ~/frame-sweep-out2
SWEEP_NOWIPE=1 SWEEP_WORKDIR=$HOME/fp-change python3 ~/sitl-frame-motor-sweep.py ~/ap-snapshot ~/frame-sweep-out2 quad 2>&1 | tee ~/frame-sweep2.console.txt
pkill -f build/sitl/bin/ardu
mkdir -p "$DEST"
cp ~/frame-sweep-out2/*.csv "$DEST/"
cp ~/frame-sweep2.console.txt "$DEST/console.txt"
cp ~/fp-change/sitl.log "$DEST/sitl-restart.log"
