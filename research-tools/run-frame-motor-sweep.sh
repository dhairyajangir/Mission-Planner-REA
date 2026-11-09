#!/bin/bash
# Run the per-frame motor test sweep in Ubuntu-E and copy the evidence into the repository. Simulator only.
# usage: bash run-frame-motor-sweep.sh [frame names ...]      (no names = the default list in sitl-frame-motor-sweep.py)
REPO='/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload'
DEST="$REPO/sitl-evidence/${SWEEP_EVIDENCE:-frame-motor-sweep}"
source ~/venv-ap/bin/activate
cp "$REPO/research-tools/sitl-frame-motor-sweep.py" ~/sitl-frame-motor-sweep.py
rm -rf ~/frame-sweep ~/frame-sweep-out
python3 ~/sitl-frame-motor-sweep.py ~/ap-snapshot ~/frame-sweep-out "$@" 2>&1 | tee ~/frame-sweep.console.txt
pkill -f build/sitl/bin/ardu
mkdir -p "$DEST"
cp ~/frame-sweep-out/* "$DEST/"
cp ~/frame-sweep.console.txt "$DEST/console.txt"
echo "copied to $DEST"
