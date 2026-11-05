#!/bin/sh
set -eu
base="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
source="$base/../ardupilot-source/ardupilot-master"
cd "$source"
export PYTHONPATH="$base/python${PYTHONPATH:+:$PYTHONPATH}"
python3 waf configure --board sitl --no-submodule-update
