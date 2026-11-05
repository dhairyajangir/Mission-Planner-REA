#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 6210)); s.close()'
mkdir -p log-list-probe
cd log-list-probe
exec timeout 95 ../arducopter -I 45 --model quad --home=-35.363261,149.165230,584,0
