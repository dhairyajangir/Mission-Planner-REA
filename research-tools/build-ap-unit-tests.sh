#!/bin/bash
# Build and run ArduPilot's own unit tests (gtest, via waf) from the PINNED snapshot, in WSL. Not a flight or SITL test.
# The snapshot is copied without modules/ChibiOS and modules/gsoap (not needed for the SITL board). The repository's ./waf is a
# symlink Windows cannot hold, so waf-light is called directly.
# Usage: build-ap-unit-tests.sh   (writes ~/ap-snapshot and ~/ap-tests-logs/*)
set -u
SRC='/mnt/c/Users/think/OneDrive/Documents/ChatGPT/The Drone Project/mission-planner-rea-upload/ardupilot-source/ardupilot-master'
LOG=~/ap-tests-logs
rm -rf "$LOG"; mkdir -p "$LOG"
echo "copying snapshot $(date)" > "$LOG/progress.txt"
rm -rf ~/ap-snapshot; mkdir -p ~/ap-snapshot
(cd "$SRC" && tar cf - --exclude=./modules/ChibiOS --exclude=./modules/gsoap .) | tar xf - -C ~/ap-snapshot 2>"$LOG/copy-errors.txt"
echo "copy done $(date) size $(du -sm ~/ap-snapshot | cut -f1) MB" >> "$LOG/progress.txt"
cd ~/ap-snapshot || exit 1
source ~/venv-ap/bin/activate
python3 modules/waf/waf-light configure --board sitl > "$LOG/configure.log" 2>&1
echo "configure exit=$? $(date)" >> "$LOG/progress.txt"
python3 modules/waf/waf-light check -j4 > "$LOG/check.log" 2>&1
echo "check exit=$? $(date)" >> "$LOG/progress.txt"
