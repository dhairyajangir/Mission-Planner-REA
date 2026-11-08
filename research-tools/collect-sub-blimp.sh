#!/bin/bash
D='/mnt/c/Users/think/OneDrive/Documents/ChatGPT/The Drone Project/mission-planner-rea-upload/sitl-evidence/sub-blimp-modes'
mkdir -p "$D"
cp ~/modesweep/sub/copter-air-modes.csv "$D/sub-modes.csv"
cp ~/modesweep/sub/copter-air-modes.json "$D/sub-modes.json"
cp ~/modesweep/sub/sitl.log "$D/sub-sitl.log"
cp ~/modesweep/blimp_run/copter-air-modes.csv "$D/blimp-modes.csv"
cp ~/modesweep/blimp_run/copter-air-modes.json "$D/blimp-modes.json"
cp ~/modesweep/blimp_run/sitl.log "$D/blimp-sitl.log"
ls "$D"
