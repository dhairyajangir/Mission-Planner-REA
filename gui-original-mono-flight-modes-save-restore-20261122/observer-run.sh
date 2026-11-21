#!/bin/bash
set -euo pipefail
echo "Begin read-only SERIAL1 observer: $(date -u +%FT%TZ)"
for ((i=0;i<180;i++)); do
    if { exec 7<>/dev/tcp/127.0.0.1/5762; } 2>/dev/null; then break; fi
    sleep 1
done
for ((n=1;n<=10;n++)); do
    marker="/evidence/observe-$n"
    if ((n>1)); then
        for ((i=0;i<600;i++)); do
            [[ -f "$marker" ]] && break
            timeout 1 cat <&7 >/dev/null || [[ $? == 124 ]]
        done
        [[ -f "$marker" ]] || break
    fi
    raw="/evidence/serial1-$n.bin"
    printf '%s capture %s\n' "$(date -u +%FT%TZ)" "$raw"
    timeout 12 cat <&7 >"$raw" &
    capture=$!
    sleep 1
    cat /observer/requests.bin >&7
    sleep 4
    cat /observer/requests.bin >&7
    wait "$capture" || [[ $? == 124 ]]
    wc -c "$raw"
    touch "/evidence/observed-$n"
done
