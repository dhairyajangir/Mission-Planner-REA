#!/bin/bash
D='/mnt/c/Users/think/OneDrive/Documents/ChatGPT/The Drone Project/mission-planner-rea-upload/sitl-evidence/tracker-auto'
mkdir -p "$D"
cp ~/modesweep/trk/tracker-auto.csv ~/modesweep/trk/tracker-auto.json ~/modesweep/trk/sitl.log "$D/"
ls "$D"
