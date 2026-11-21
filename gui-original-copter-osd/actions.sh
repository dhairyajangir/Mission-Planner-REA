wait_id() {
    local title="$1" found
    for ((i=0;i<150;i++)); do
        found=$(xdotool search --onlyvisible --name "$title" 2>/dev/null | tail -1) || true
        if [[ "$found" =~ ^[0-9]+$ ]]; then return 0; fi
        kill -0 "$app_pid" || break
        sleep 1
    done
    snapshot blocked
    return 1
}
wait_log() {
    for ((i=0;i<90;i++)); do
        if grep -Fq "$1" /evidence/release.log; then return 0; fi
        kill -0 "$app_pid" || break
        sleep 1
    done
    snapshot blocked
    return 1
}
act() {
    printf '%s click %s %s %s\n' "$(date -u +%FT%TZ)" "$1" "$2" "$3"
    xdotool mousemove "$1" "$2" click 1
    sleep 3
}
if [[ "${MANUAL:-0}" == 1 ]]; then
    wait_id '^TCP$'
    act 1140 122 connect
    wait_id '^remote host$'
    xdotool key ctrl+a
    xdotool type '127.0.0.1'
    xdotool key Return
    wait_id '^remote Port$'
    xdotool key ctrl+a
    xdotool type '5760'
    xdotool key Return
fi
wait_id 'ArduCopter V4.8.0-dev'
# The completed packed parameter download precedes setup-page registration.
wait_log 'Done 0 15968'
snapshot connected
act 207 116 setup
wait_log 'Open MissionPlanner.GCSViews.InitialSetup'
act 160 224 optional
wait_log 'Open MissionPlanner.GCSViews.ConfigurationView.ConfigOptional'
snapshot optional
act 143 643 hardware-osd
wait_log 'Open MissionPlanner.GCSViews.ConfigurationView.ConfigHWOSD OSD'
xdotool mousemove 1240 765
sleep 5
snapshot hardware-osd
act 263 116 config
wait_log 'Open MissionPlanner.GCSViews.SoftwareConfig'
sleep 3
snapshot config
sleep 6
mkdir -p /evidence/telemetry
find "$HOME" -name '*.tlog' -type f -exec cp {} /evidence/telemetry/ \;
date -u
