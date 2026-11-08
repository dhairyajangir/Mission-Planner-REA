#!/bin/bash
D='/mnt/c/Users/think/OneDrive/Documents/ChatGPT/The Drone Project/mission-planner-rea-upload/sitl-evidence/plane-modes'
mkdir -p "$D"
cp ~/modesweep/pl/copter-air-modes.csv "$D/plane-modes.csv"
cp ~/modesweep/pl/copter-air-modes.json "$D/plane-modes.json"
cp ~/modesweep/pl/sitl.log "$D/sitl.log"
ls -l "$D"
