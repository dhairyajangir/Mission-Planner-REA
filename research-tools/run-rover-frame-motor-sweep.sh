#!/bin/bash
# Run the ArduRover frame motor sweep in Ubuntu-E and copy the evidence into the repository. Simulator only.
# SWEEP_INSTANCE=1 runs it on tcp 5770 so that it can run beside another autotest on 5760.
REPO='/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload'
DEST="$REPO/sitl-evidence/${SWEEP_EVIDENCE:-rover-frame-motor-sweep}"
source ~/venv-ap/bin/activate
cp "$REPO/research-tools/sitl-rover-frame-motor-sweep.py" ~/sitl-rover-frame-motor-sweep.py
rm -rf ~/rover-sweep ~/rover-sweep-out
python3 ~/sitl-rover-frame-motor-sweep.py ~/ap-snapshot ~/rover-sweep-out "$@" 2>&1 | tee ~/rover-sweep.console.txt
mkdir -p "$DEST"
cp ~/rover-sweep-out/* "$DEST/"
cp ~/rover-sweep.console.txt "$DEST/console.txt"
for d in ~/rover-sweep/*/; do cp "$d/sitl.log" "$DEST/sitl-$(basename $d).log" 2>/dev/null; done
echo "copied to $DEST"
