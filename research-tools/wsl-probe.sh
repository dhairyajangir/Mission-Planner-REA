#!/bin/sh
set +e
for package in pymavlink pexpect future lxml yaml; do
  python3 -c "import importlib.util; print('$package', bool(importlib.util.find_spec('$package')))"
done
for binary in sim_vehicle.py cmake ninja git gcc g++ ccache; do
  command -v "$binary" || true
done
df -h / | tail -1
