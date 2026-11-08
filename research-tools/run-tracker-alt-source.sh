#!/bin/bash
# Re-run the AntennaTracker SITL AUTO test with each ALT_SOURCE setting (disposable simulator only).
# Output is written to WSL ~/tracker-alt and copied to the repository by the caller.
source ~/venv-ap/bin/activate
BIN=$(ls ~/modesweep/antennatracker ~/modesweep/*racker* 2>/dev/null | head -1)
SCRIPT='/mnt/c/Users/think/OneDrive/Documents/ChatGPT/The Drone Project/mission-planner-rea-upload/research-tools/sitl-tracker-auto.py'
echo "binary=$BIN"
rm -rf ~/tracker-alt; mkdir -p ~/tracker-alt
# name:alt_source:extra
for cfg in "baro-no-pressure:0:" "baro-with-pressure:0:baro" "gps:1:" "gps-vehicle-only:2:"; do
  IFS=: read -r name src extra <<< "$cfg"
  echo "=== $name ALT_SOURCE=$src $extra"
  pkill -f antennatracker 2>/dev/null; sleep 1
  python3 "$SCRIPT" "$BIN" ~/tracker-alt/$name $src $extra 2>&1 | tail -6
done
echo done
