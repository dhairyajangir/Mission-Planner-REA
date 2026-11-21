#!/usr/bin/env bash
set -euo pipefail
base=$(dirname "$0")
dest=/tmp/mission-planner-original-gui-nov21/observer-input
mkdir -p "$dest"
~/venv-ap/bin/python "$base/observe-telemetry.py" generate "$dest/requests.bin"
cp "$base/observer-run.sh" "$dest/run-pending"
chmod 700 "$dest/run-pending"
(cd "$dest" && sha256sum requests.bin run-pending | sed 's/  run-pending$/  run/' > manifest.sha256)
mv "$dest/run-pending" "$dest/run"
