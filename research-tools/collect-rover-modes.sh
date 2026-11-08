#!/bin/bash
D='/mnt/c/Users/think/OneDrive/Documents/ChatGPT/The Drone Project/mission-planner-rea-upload/sitl-evidence/rover-modes'
mkdir -p "$D"
cp ~/modesweep/rov/copter-air-modes.csv "$D/rover-modes.csv"
cp ~/modesweep/rov/copter-air-modes.json "$D/rover-modes.json"
cp ~/modesweep/rov/sitl.log "$D/sitl.log"
ls -l "$D"
