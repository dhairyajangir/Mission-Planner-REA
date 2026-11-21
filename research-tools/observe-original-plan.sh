#!/usr/bin/env bash
# Run from Ubuntu-E. Each invocation of "start" owns a unique extraction and bubblewrap namespace.
set -euo pipefail
base=/tmp/mission-planner-original-gui-nov21
repo=$(cd "$(dirname "$0")/.." && pwd)
if [[ ${1:-} == start ]]; then
    runtime="$base/root"
    app=$(mktemp -d "$base/plan-app-XXXXXXXX")
    run=$(mktemp -d "$base/results/plan-XXXXXXXX")
    echo "Guest evidence: $run"
    unzip -qo "$repo/mission-planner-portable.zip" -d "$app"
    (cd "$app" && echo 'a49e30e2cd635836cd737f112f419da2d3c46c59716ee08122e2986013b79f2a  MissionPlanner.exe' | sha256sum -c -)
    echo "$app" > "$run/extraction.txt"
    cp "$0" "$run/observe.sh"
    exec "$runtime/usr/bin/bwrap" --die-with-parent --new-session --unshare-all --cap-drop ALL --clearenv \
        --ro-bind "$runtime" / --proc /proc --dev /dev --tmpfs /tmp --tmpfs /home/test --tmpfs /var/lib/xkb \
        --bind "$app" /opt/mp --bind "$run" /evidence --chdir /opt/mp \
        --setenv HOME /home/test --setenv USER test --setenv LANG C.UTF-8 --setenv PATH /usr/bin:/bin \
        --setenv XDG_CONFIG_HOME /home/test/.config --setenv XDG_DATA_HOME /home/test/.local/share \
        --setenv DISPLAY :36 --setenv LIBGL_ALWAYS_SOFTWARE 1 /bin/bash /evidence/observe.sh guest
elif [[ ${1:-} == guest ]]; then
    exec > /evidence/observation.log 2>&1
    date -u; cat /proc/net/dev; ls -l /dev; mono --version
    sha256sum MissionPlanner.exe MissionPlanner.Utilities.dll MissionPlanner.Comms.dll MissionPlanner.Controls.dll
    mkdir -p /tmp/.X11-unix "$XDG_CONFIG_HOME" "$XDG_DATA_HOME/Mission Planner"
    chmod 1777 /tmp/.X11-unix
    plugins=$(find /opt/mp/plugins -maxdepth 1 -type f \( -iname '*.cs' -o -iname '*.dll' \) -printf '%f\n' | tr '[:upper:]' '[:lower:]' | sort | paste -sd ';')
    printf '<?xml version="1.0" encoding="utf-8"?>\n<Config><DisabledPlugins>%s</DisabledPlugins></Config>\n' "$plugins" >"$XDG_DATA_HOME/Mission Planner/config.xml"
    cp "$XDG_DATA_HOME/Mission Planner/config.xml" /evidence/initial-user-config.xml
    printf 'QGC WPL 110\n0\t1\t0\t16\t0\t0\t0\t0\t-35.363260\t149.165230\t584\t1\n1\t0\t3\t16\t0\t0\t0\t0\t-35.362700\t149.165900\t23\t1\n2\t0\t3\t16\t0\t0\t0\t0\t-35.362100\t149.166400\t37\t1\n' >"$HOME/plan-readback.waypoints"
    cp "$HOME/plan-readback.waypoints" /evidence/input.waypoints
    Xvfb "$DISPLAY" -screen 0 1280x800x24 -nolisten tcp > /evidence/xvfb.log 2>&1 &
    server=$!
    trap 'kill "$server" 2>/dev/null || true' EXIT
    for ((i=0;i<30;i++)); do if xdpyinfo >/dev/null 2>&1; then break; fi; sleep 0.2; done
    mono MissionPlanner.exe >/evidence/release.log 2>&1 &
    mp=$!
    trap 'kill "$mp" "$server" 2>/dev/null || true' EXIT
    for ((i=0;i<110;i++)); do if grep -Fq 'appload time' /evidence/release.log; then break; fi; sleep 1; done
    snapshot() { xwininfo -root -tree >"/evidence/$1-tree.txt"; xwd -silent -root -out "/evidence/$1.xwd"; }
    sleep 5
    snapshot startup
    for ((step=1;step<=36;step++)); do
        for ((i=0;i<480;i++)); do [[ -f /evidence/action-$step ]] && break; kill -0 "$mp"; sleep 1; done
        read -r verb x y label <"/evidence/action-$step"
        [[ "$verb" == finish ]] && break
        [[ "$label" =~ ^[a-z0-9-]+$ ]]
        case "$verb" in
            click|right)
                [[ "$x" =~ ^[0-9]+$ && "$y" =~ ^[0-9]+$ && "$x" -lt 1280 && "$y" -lt 800 ]]
                button=1; [[ "$verb" == right ]] && button=3
                xdotool mousemove "$x" "$y" click "$button";;
            fixture) xdotool key ctrl+a; xdotool type -- "$HOME/plan-readback.waypoints";;
            output) xdotool key ctrl+a; xdotool type -- "$HOME/plan-saved.waypoints";;
            enter) xdotool key Return;;
            escape) xdotool key Escape;;
            *) exit 2;;
        esac
        printf '%s %s %s %s %s\n' "$step" "$verb" "$x" "$y" "$label"
        sleep 4; snapshot "$label"
    done
    if [[ -f "$HOME/plan-saved.waypoints" ]]; then cp "$HOME/plan-saved.waypoints" /evidence/saved.waypoints; fi
else
    echo "Usage: bash $0 start" >&2; exit 2
fi
