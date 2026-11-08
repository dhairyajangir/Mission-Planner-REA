#!/bin/bash
# Second stage of build-ap-unit-tests.sh: the snapshot copy has no .git, but the waf build calls git for version headers.
# Create a throwaway empty repository (its commit hash is NOT the pinned ArduPilot commit) and run `waf check`.
set -u
LOG=~/ap-tests-logs
cd ~/ap-snapshot || exit 1
source ~/venv-ap/bin/activate
if [ ! -d .git ]; then
  git init -q . && git -c user.name=t -c user.email=t@t commit -q --allow-empty -m "throwaway repository for version headers (not the pinned commit)"
fi
echo "check started $(date)" >> "$LOG/progress.txt"
python3 modules/waf/waf-light check -j6 > "$LOG/check.log" 2>&1
echo "check exit=$? $(date)" >> "$LOG/progress.txt"
