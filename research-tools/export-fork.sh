#!/bin/bash
# Export the fork's own commits (baseline..ours) as patch files into the evidence repository, and a git bundle of the whole fork to E:.
REPO='/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload'
cd ~/ardupilot-fork || exit 1
rm -rf "$REPO/fork-patches"; mkdir -p "$REPO/fork-patches"
git format-patch -q baseline-72b23820..ours -o "$REPO/fork-patches"
git log --oneline baseline-72b23820..ours > "$REPO/fork-patches/COMMITS.txt"
git rev-parse baseline-72b23820 > "$REPO/fork-patches/BASELINE.txt"
git bundle create /mnt/e/DroneProject/ardupilot-fork.bundle --all 2>&1 | tail -1
git bundle verify /mnt/e/DroneProject/ardupilot-fork.bundle 2>&1 | tail -2
ls -la "$REPO/fork-patches" | cut -c1-110
ls -la /mnt/e/DroneProject/ardupilot-fork.bundle | cut -c1-100
