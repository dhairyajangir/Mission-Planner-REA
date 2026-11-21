#!/usr/bin/env bash
set -euo pipefail
exec > /evidence/observation.log 2>&1
date -u
cat /proc/net/dev
ls -l /dev
mono --version
sha256sum MissionPlanner.exe MissionPlanner.Utilities.dll MissionPlanner.Comms.dll MissionPlanner.Controls.dll
mkdir -p "$HOME/.config" "$HOME/.local/share" /tmp/.X11-unix
chmod 1777 /tmp/.X11-unix
Xvfb "$DISPLAY" -screen 0 1280x800x24 -nolisten tcp > /evidence/xvfb.log 2>&1 &
display_pid=$!
trap 'kill "$display_pid" 2>/dev/null || true' EXIT
for ((i=0;i<30;i++)); do
    if xdpyinfo >/dev/null 2>&1; then break; fi
    sleep 0.2
done
xdpyinfo >/evidence/display.txt
if [[ "${USE_COPTER:-0}" == 1 ]]; then
    sha256sum /sim/arducopter
    (cd /sim && exec ./arducopter --model +) > /evidence/copter.log 2>&1 &
    sitl_pid=$!
    (
        until [[ -x /observer/run ]]; do sleep 1; done
        cd /observer
        sha256sum --check manifest.sha256
        exec /observer/run
    ) >/evidence/observer.log 2>&1 &
    observer_pid=$!
fi
if [[ "${SKIP_STARTUP_PLUGINS:-0}" == 1 ]]; then
    xdotool keydown Shift_L
    echo 'Holding Shift during startup (built-in skip-plugin path).'
elif [[ "${SKIP_STARTUP_PLUGINS:-0}" == 2 ]]; then
    profile="$XDG_DATA_HOME/Mission Planner"
    mkdir -p "$profile"
    plugins=$(find /opt/mp/plugins -maxdepth 1 -type f \( -iname '*.cs' -o -iname '*.dll' \) -printf '%f\n' | tr '[:upper:]' '[:lower:]' | sort | paste -sd ';')
    printf '<?xml version="1.0" encoding="utf-8"?>\n<Config><DisabledPlugins>%s</DisabledPlugins></Config>\n' "$plugins" >"$profile/config.xml"
    cp "$profile/config.xml" /evidence/initial-user-config.xml
    echo 'Preloaded only DisabledPlugins in the fresh guest profile.'
fi
mono MissionPlanner.exe >/evidence/release.log 2>&1 &
app_pid=$!
trap 'kill "$app_pid" "$display_pid" ${sitl_pid:+"$sitl_pid"} ${observer_pid:+"$observer_pid"} 2>/dev/null || true' EXIT
snapshot() {
    xwininfo -root -tree > "/evidence/windows-$1.txt"
    xwd -silent -root -out "/evidence/screen-$1.xwd"
}
if [[ "${SKIP_STARTUP_PLUGINS:-0}" == 1 ]]; then
    sleep 38
    xdotool keyup Shift_L
    echo 'Released Shift.'
elif [[ "${SKIP_STARTUP_PLUGINS:-0}" == 2 ]]; then
    for ((i=0;i<100;i++)); do
        if grep -Fq 'appload time' /evidence/release.log; then break; fi
        sleep 1
    done
else
for ((i=0;i<120;i++)); do
    if xdotool search --onlyvisible --name 'Restart Mission Planner to enable Drone ID Tab' >/dev/null 2>&1; then
        snapshot drone-id
        xdotool mousemove 523 94 click 1
        echo "Dismissed observed Drone ID informational message at (523,94)."
        break
    fi
    sleep 1
done
fi
sleep 6
snapshot startup
# An operator reads each captured screen before specifying the next point.
for ((step=1;step<=40;step++)); do
    for ((poll=0;poll<360;poll++)); do
        [[ -e "/evidence/action-$step" ]] && break
        kill -0 "$app_pid" 2>/dev/null || exit 2
        sleep 1
    done
    [[ -e "/evidence/action-$step" ]] || break
    read -r x y label < "/evidence/action-$step"
    [[ "$x" != done ]] || break
    [[ "$x" =~ ^[0-9]{1,4}$ && "$y" =~ ^[0-9]{1,3}$ && "$label" =~ ^[a-z0-9-]+$ && "$x" -lt 1280 && "$y" -lt 800 ]]
    printf '%s: click (%s,%s) label %s\n' "$(date -u +%FT%TZ)" "$x" "$y" "$label"
    xdotool mousemove "$x" "$y" click 1
    sleep 4
    snapshot "$label"
done
if [[ "${USE_COPTER:-0}" == 1 ]]; then
    mkdir -p /evidence/telemetry
    find "$HOME" -name '*.tlog' -type f -exec cp {} /evidence/telemetry/ \;
fi
ls -a "$HOME"
