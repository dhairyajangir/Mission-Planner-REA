#!/bin/bash
# Create the baseline of our own ArduPilot fork inside Ubuntu-E: ~/ardupilot-fork, a git repository whose first commit is the
# pinned upstream snapshot (commit 72b238201f5ea3b556e3809b2ec704fcf701474a) with no changes. ArduPilot is GPLv3; the licence files
# are kept. Our own changes go in later commits on branch "ours".
set -e
SRC='/mnt/e/DroneProject/The Drone Project/ardupilot-source/ardupilot-master'
DST=~/ardupilot-fork
if [ -d "$DST/.git" ]; then echo "fork already exists"; git -C "$DST" log --oneline | head -3; exit 0; fi
mkdir -p "$DST"
# build outputs and VCS metadata are not part of the source
rsync -a --exclude '.git' --exclude 'build' --exclude '__pycache__' "$SRC"/ "$DST"/
cd "$DST"
git init -q
git config user.name "ardupilot-rea fork"
git config user.email "fork@localhost"
git checkout -q -b upstream-snapshot
git add -A >/dev/null 2>&1
git commit -q -m "Baseline: ArduPilot snapshot 72b238201f5ea3b556e3809b2ec704fcf701474a (unchanged upstream tree)"
git tag baseline-72b23820
git checkout -q -b ours
echo "files: $(git ls-files | wc -l)"
git log --oneline | head -3
du -sh "$DST" | cut -f1
