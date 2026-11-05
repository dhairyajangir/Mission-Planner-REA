#!/bin/sh
set -eu
cd "$(dirname "$0")"
chmod u+x ./arducopter
./arducopter --help
