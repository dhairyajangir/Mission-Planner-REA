#!/bin/bash
# Run the ArduSub frame-configuration motor sweep in Ubuntu-E and copy the evidence into the repository. Simulator only.
# SWEEP_INSTANCE=1 runs it on tcp 5770 so that it can run beside another autotest on 5760.
REPO='/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload'
DEST="$REPO/sitl-evidence/${SWEEP_EVIDENCE:-sub-frame-motor-sweep}"
source ~/venv-ap/bin/activate
cp "$REPO/research-tools/sitl-sub-frame-motor-sweep.py" ~/sitl-sub-frame-motor-sweep.py
rm -rf ~/sub-sweep ~/sub-sweep-out
python3 ~/sitl-sub-frame-motor-sweep.py ~/ap-snapshot ~/sub-sweep-out 2>&1 | tee ~/sub-sweep.console.txt
mkdir -p "$DEST"
cp ~/sub-sweep-out/* "$DEST/"
cp ~/sub-sweep.console.txt "$DEST/console.txt"
for d in ~/sub-sweep/*/; do cp "$d/sitl.log" "$DEST/sitl-config-$(basename $d).log" 2>/dev/null; done
echo "copied to $DEST"
