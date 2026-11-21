# Runs in the startup script's own isolated display.
wait_id() {
    local title="$1" found
    for ((i=0;i<65;i++)); do
        found=$(xdotool search --onlyvisible --name "$title" 2>/dev/null | tail -1) || true
        if [[ "$found" =~ ^[0-9]+$ ]]; then echo "$found"; return 0; fi
        sleep 1
    done
    snapshot blocked
    return 1
}
say() { echo "$(date -u +%FT%TZ) $*"; }
say 'Click HELP then open Ctrl+F tools'
xdotool mousemove 390 117 click 1
sleep 3
xdotool key ctrl+f
wait_id '^Create custom audio warnings$' >/dev/null
sleep 2
snapshot tools
say 'Click Geo ref images in tools'
xdotool mousemove 95 43 click 1
wait_id '^Browse Pictures$' >/dev/null
sleep 3
xdotool mousemove 1250 785
snapshot georef
window=$(xdotool search --onlyvisible --maxdepth 1 --name '^Geo Ref Images$' | tail -1)
[[ "$window" =~ ^[0-9]+$ ]]
say 'Resize Geo Ref Images for repaint'
xdotool windowmove "$window" 8 8
xdotool windowsize "$window" 1180 730
sleep 3
snapshot georef-visible
radio=$(wait_id '^Time offset$')
say 'Select Time offset'
xdotool mousemove --window "$radio" 8 8 click 1
xdotool mousemove 1250 785
sleep 2
snapshot offset
say 'Finished with inputs empty'
