#!/usr/bin/env bash
# Run under the existing project Ubuntu-E distro. Each test gets independent device/network/process namespaces.
set -euo pipefail
if [[ ${1:-} != guest ]]; then
    lane=$(cd "$(dirname "$0")" && pwd)
    repo=$(dirname "$lane")
    work=/tmp/mission-planner-original-gui-nov21
    root="$work/root"
    app=$(mktemp -d "$work/battery-app-XXXXXXXX")
    out=$(mktemp -d "$work/results/batterytrace-XXXXXXXX")
    echo "Evidence directory: $out"
    unzip -qo "$repo/mission-planner-portable.zip" -d "$app"
    sim=/home/think/ap-snapshot/build/sitl/bin/arducopter
    [[ "$(sha256sum "$app/MissionPlanner.exe" | cut -d' ' -f1)" == a49e30e2cd635836cd737f112f419da2d3c46c59716ee08122e2986013b79f2a ]]
    [[ "$(sha256sum "$sim" | cut -d' ' -f1)" == 24afb2e186bcdf66c66d7cb5b88fb7afeaa2a0b89bf63c9d58e4fb2029ac2b54 ]]
    cp "$lane/run.sh" "$out/run.sh"
    cp "$repo/gui-original-copter-sensors/sensors-FjBlM50a/initial-user-config.xml" "$out/profile.xml"
    "$root/usr/bin/bwrap" --die-with-parent --new-session --unshare-all --cap-drop ALL --clearenv \
        --ro-bind "$root" / --proc /proc --dev /dev --tmpfs /tmp --tmpfs /home/test --tmpfs /var/lib/xkb \
        --tmpfs /sim --ro-bind "$sim" /sim/arducopter --bind "$app" /opt/mp --bind "$out" /evidence \
        --chdir /opt/mp --setenv HOME /home/test --setenv USER test --setenv LANG C.UTF-8 --setenv PATH /usr/bin:/bin \
        --setenv XDG_CONFIG_HOME /home/test/.config --setenv XDG_DATA_HOME /home/test/.local/share \
        --setenv DISPLAY :39 --setenv LIBGL_ALWAYS_SOFTWARE 1 /bin/bash /evidence/run.sh guest
    python3 "$repo/gui-original-mono-evidence-20261122/runtime/compare_archive.py" "$repo/mission-planner-portable.zip" "$app" "$out/zip.json"
    dest="$lane/$(basename "$out")"
    mkdir "$dest"
    cp "$out"/{observation.log,profile.xml,wire.tlog.gz,release.log.gz,zip.json} "$dest/"
    exit 0
fi
exec > /evidence/observation.log 2>&1
date -u; mono --version; cat /proc/net/dev
mkdir -p /tmp/.X11-unix "$XDG_DATA_HOME/Mission Planner" "$XDG_CONFIG_HOME"
chmod 1777 /tmp/.X11-unix
cp /evidence/profile.xml "$XDG_DATA_HOME/Mission Planner/config.xml"
Xvfb "$DISPLAY" -screen 0 1280x800x24 -nolisten tcp >/evidence/xvfb.log 2>&1 &
xp=$!
(cd /sim && exec ./arducopter --model +) >/evidence/copter.log 2>&1 &
sp=$!
trap 'kill "$xp" "$sp" 2>/dev/null || true' EXIT
for ((i=0;i<40;i++)); do if xdpyinfo >/dev/null 2>&1; then break; fi; sleep .2; done
mono --trace=T:MissionPlanner.GCSViews.ConfigurationView.ConfigBatteryMonitoring MissionPlanner.exe >/evidence/release.log 2>&1 &
mp=$!
trap 'kill "$mp" "$sp" "$xp" 2>/dev/null || true' EXIT
waitlog() {
    for ((i=0;i<120;i++)); do if grep -Fq "$1" /evidence/release.log; then return; fi; kill -0 "$mp"; sleep 1; done
    echo "Missing $1"; exit 1
}
act() {
    printf '%s %s (%s,%s)\n' "$(date -u +%FT%T.%NZ)" "$3" "$1" "$2"
    xdotool mousemove "$1" "$2" click 1
    sleep 4
}
waitlog 'appload time'
for ((i=0;i<100;i++)); do if xdotool search --onlyvisible --name 'ArduCopter V4.8.0-dev' >/dev/null 2>&1; then break; fi; sleep 1; done
xdotool search --onlyvisible --name 'ArduCopter V4.8.0-dev'
act 207 116 setup
waitlog 'Open MissionPlanner.GCSViews.InitialSetup'
act 163 194 mandatory
waitlog 'Open MissionPlanner.GCSViews.ConfigurationView.ConfigMandatory'
act 158 583 optional
waitlog 'Open MissionPlanner.GCSViews.ConfigurationView.ConfigOptional'
act 249 505 scroll-only
act 153 223 battery
waitlog 'Open MissionPlanner.GCSViews.ConfigurationView.ConfigBatteryMonitoring Battery Monitor'
sleep 17
act 108 116 leave-for-data
sleep 6
find "$HOME" -name '*.tlog' -type f -exec gzip -c '{}' \; >/evidence/wire.tlog.gz
kill "$mp" 2>/dev/null || true
wait "$mp" || true
gzip -c /evidence/release.log >/evidence/release.log.gz
