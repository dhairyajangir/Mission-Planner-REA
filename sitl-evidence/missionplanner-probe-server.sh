#!/bin/sh
set -eu
cd "$(dirname "$0")"
mkdir -p missionplanner-probe
cd missionplanner-probe
exec timeout 90 ../arducopter -I 40 --model quad --home=-35.363261,149.165230,584,0
