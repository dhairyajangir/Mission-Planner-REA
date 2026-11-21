#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
evidence="$repo/gui-original-copter-sensors"
work=/tmp/mission-planner-original-gui-nov21
root="$work/root"
[[ -e "$root/bin/sh" ]] || ln -s bash "$root/usr/bin/sh"
app=$(mktemp -d "$work/app-XXXXXXXX")
unzip -qo "$repo/mission-planner-portable.zip" -d "$app"
[[ "$(sha256sum "$app/MissionPlanner.exe" | cut -d' ' -f1)" == a49e30e2cd635836cd737f112f419da2d3c46c59716ee08122e2986013b79f2a ]]
out=$(mktemp -d "$work/results/sensors-XXXXXXXX")
printf 'Observation directory %s\n' "$out"
printf '%s\n' "$app" >"$out/extracted-path.txt"
skip_plugins=0
connected=0
guest_inputs=()
if [[ "${1:-}" == --skip-plugins ]]; then skip_plugins=1; fi
if [[ "${1:-}" == --profile-no-plugins ]]; then skip_plugins=2; fi
if [[ "${1:-}" == --copter ]]; then
    skip_plugins=2
    connected=1
    sim=/home/think/ap-snapshot/build/sitl/bin/arducopter
    [[ "$(sha256sum "$sim" | cut -d' ' -f1)" == 24afb2e186bcdf66c66d7cb5b88fb7afeaa2a0b89bf63c9d58e4fb2029ac2b54 ]]
    observer=$(mktemp -d "$work/sensors-observer-XXXXXXXX")
    guest_inputs=(--tmpfs /sim --ro-bind "$sim" /sim/arducopter --ro-bind "$observer" /observer)
fi
cp "$evidence/capture.sh" "$out/capture.sh"
exec "$root/usr/bin/bwrap" --die-with-parent --new-session --unshare-all --cap-drop ALL --clearenv \
  --ro-bind "$root" / --proc /proc --dev /dev --tmpfs /tmp --tmpfs /home/test --tmpfs /var/lib/xkb \
  "${guest_inputs[@]}" \
  --bind "$app" /opt/mp --bind "$out" /evidence --chdir /opt/mp \
  --setenv HOME /home/test --setenv USER test --setenv LANG C.UTF-8 --setenv PATH /usr/bin:/bin \
  --setenv XDG_CONFIG_HOME /home/test/.config --setenv XDG_DATA_HOME /home/test/.local/share \
  --setenv DISPLAY :29 --setenv SKIP_STARTUP_PLUGINS "$skip_plugins" --setenv USE_COPTER "$connected" \
  --setenv LIBGL_ALWAYS_SOFTWARE 1 /bin/bash /evidence/capture.sh
