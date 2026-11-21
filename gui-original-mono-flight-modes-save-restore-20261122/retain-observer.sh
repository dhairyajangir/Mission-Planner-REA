#!/usr/bin/env bash
set -euo pipefail
run=$1
step=$2
dest=$3
[[ $run =~ ^run-[A-Za-z0-9]{8}$ && $step =~ ^[1-9][0-9]?$ ]]
base=$(dirname "$0")
src="/tmp/mission-planner-original-gui-nov21/results/$run"
mkdir -p "$dest"
if [[ ! -f "$src/observed-$step" ]]; then
    touch "$src/observe-$step"
    for ((i=0;i<45;i++)); do
        [[ -f "$src/observed-$step" ]] && break
        sleep 1
    done
fi
[[ -f "$src/observed-$step" ]]
cp "$src/serial1-$step.bin" "$dest/serial1-$step.bin"
~/venv-ap/bin/python "$base/observe-telemetry.py" decode "$dest/serial1-$step.bin" > "$dest/serial1-$step.json"
cp "$src/observer.log" "$dest/observer.log"
python3 - "$dest/serial1-$step.json" <<'PY'
import json,sys
data=json.load(open(sys.argv[1]))
records=data["records"]
print("heartbeats",data["message_counts"].get("HEARTBEAT"),"armed states", sorted(set(r["armed"] for r in records if r["kind"]=="HEARTBEAT")))
print({r["name"]: r["value"] for r in records if r["kind"]=="PARAM_VALUE"})
PY
