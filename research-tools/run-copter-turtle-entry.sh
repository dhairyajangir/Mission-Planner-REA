#!/bin/bash
# Run sitl-copter-turtle-entry.py against the Copter SITL binary in ~/ap-snapshot (disposable simulator only) and copy the result into the repository.
source ~/venv-ap/bin/activate
REPO='/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload'
BIN=~/ap-snapshot/build/sitl/bin/arducopter
pkill -f 'build/sitl/bin/ardu' 2>/dev/null; sleep 1
rm -rf ~/copter-turtle; mkdir -p ~/copter-turtle
echo "binary: $(ls -la $BIN | cut -c1-90)" > ~/copter-turtle/run-info.txt
python3 "$REPO/research-tools/sitl-copter-turtle-entry.py" "$BIN" ~/copter-turtle 2>&1 | tail -8
mkdir -p "$REPO/sitl-evidence/copter-turtle-entry"
cp ~/copter-turtle/turtle-entry.csv ~/copter-turtle/turtle-entry.json ~/copter-turtle/sitl.log ~/copter-turtle/run-info.txt "$REPO/sitl-evidence/copter-turtle-entry/" 2>/dev/null
echo copied
