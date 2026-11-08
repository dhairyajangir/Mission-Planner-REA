#!/bin/bash
# Run sitl-copter-stick-modes.py against the Copter SITL binary built in ~/ap-snapshot (disposable simulator only) and
# copy the result into the repository evidence folder.
source ~/venv-ap/bin/activate
REPO='/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload'
BIN=~/ap-snapshot/build/sitl/bin/arducopter
pkill -f 'build/sitl/bin/ardu' 2>/dev/null; sleep 1
rm -rf ~/copter-stick; mkdir -p ~/copter-stick
echo "binary: $(ls -la $BIN | cut -c1-80)" > ~/copter-stick/run-info.txt
python3 "$REPO/research-tools/sitl-copter-stick-modes.py" "$BIN" ~/copter-stick 2>&1 | tail -20
mkdir -p "$REPO/sitl-evidence/copter-stick-modes"
cp ~/copter-stick/copter-stick-modes.csv ~/copter-stick/copter-stick-modes.json ~/copter-stick/sitl.log ~/copter-stick/run-info.txt "$REPO/sitl-evidence/copter-stick-modes/" 2>/dev/null
echo copied
