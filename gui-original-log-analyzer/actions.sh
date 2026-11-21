sha256sum /evidence/copter.log
grep -Fq 'appload time' /evidence/release.log
# Move to the rightmost DATA tab, as observed in the separate Log Browser capture.
xdotool mousemove 376 385 click --repeat 16 1
sleep 1
xdotool mousemove 128 397 click 1
sleep 2
snapshot analysis-menu
button=$(xdotool search --onlyvisible --name '^Auto Analysis$')
[[ "$button" =~ ^[0-9]+$ ]]
echo 'Selected DataFlash Logs > Auto Analysis in the disconnected DATA screen.'
xdotool mousemove --window "$button" 20 11 click 1
sleep 3
xdotool key ctrl+a
xdotool type '/evidence/copter.log'
sleep 1
snapshot file-picker
open=$(xdotool search --onlyvisible --name '^Open$' | tail -n 1)
[[ "$open" =~ ^[0-9]+$ ]]
echo 'Submitted /evidence/copter.log using the Open button.'
xdotool mousemove --window "$open" 20 10 click 1
sleep 2
for ((i=0;i<120;i++)); do
    if xwininfo -root -tree 2>/dev/null | grep -F 'Failed to download LogAnalyzer' >/dev/null; then
        echo 'Observed Failed to download LogAnalyzer.'
        snapshot download-result
        xdotool key Return
        sleep 3
        snapshot final-result
        exit 0
    fi
    sleep 1
done
snapshot unrecognized
echo 'No exact download-error label found in the window tree.'
