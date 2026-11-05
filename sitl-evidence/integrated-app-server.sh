#!/bin/sh
set -eu
cd "$(dirname "$0")"
instance="${SITL_INSTANCE:-46}"
port=$((5760 + instance * 10))
python3 -c 'import socket,sys; s=socket.socket(); s.bind(("127.0.0.1", int(sys.argv[1]))); s.close()' "$port"
run="${SITL_RUN_NAME:-integrated-app-probe}"
case "$run" in ''|*/*|*..*) echo 'invalid run name' >&2; exit 1;; esac
mkdir -p "$run"
cd "$run"
binary="${SITL_BINARY:-../arducopter}"
exec timeout 180 "$binary" -I "$instance" --model quad --home=-35.363261,149.165230,584,0
