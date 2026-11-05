#!/bin/sh
set -eu
base="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
source="$base/../ardupilot-source/ardupilot-master"
cd "$source"
if [ -e .git ]; then
    echo 'Refusing to replace existing Git metadata' >&2
    exit 1
fi
git init -q
git remote add origin https://github.com/ArduPilot/ardupilot.git
git -c protocol.version=2 fetch --depth=1 --filter=blob:none origin 72b238201f5ea3b556e3809b2ec704fcf701474a
git reset --mixed FETCH_HEAD
git rev-parse HEAD
