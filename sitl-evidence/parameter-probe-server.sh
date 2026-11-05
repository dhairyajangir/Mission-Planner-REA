#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 6170)); s.close()'
mkdir -p parameter-probe
cd parameter-probe
exec timeout 110 ../arducopter -I 41 --model quad --home=-35.363261,149.165230,584,0
