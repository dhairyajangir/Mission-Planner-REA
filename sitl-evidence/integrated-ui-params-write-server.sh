#!/bin/sh
set -eu
cd "$(dirname "$0")/integrated-ui-params-write"
python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 6580)); s.close()'
exec timeout 900 ../archive-built/arducopter -I 82 --model quad --home=-35.363261,149.165230,584,0
