grep -Fq 'appload time' /evidence/release.log
shopt -s nullglob
input_devices=(/dev/input/js* /dev/input/event* /dev/js* /dev/hidraw*)
echo "Input device nodes: ${#input_devices[@]}"
[[ ${#input_devices[@]} -eq 0 ]]
echo 'Clicked SETUP toolbar tab.'
xdotool mousemove 207 116 click 1
sleep 3
snapshot setup
select_row() {
    local window
    window=$(xdotool search --onlyvisible --name "$1")
    [[ "$window" =~ ^[0-9]+$ ]]
    xdotool mousemove --window "$window" 60 14 click 1
}
echo 'Clicked Optional Hardware menu row.'
select_row '^>> Optional Hardware$'
sleep 3
snapshot optional
echo 'Clicked Joystick submenu row.'
select_row '^[[:space:]]*Joystick$'
sleep 5
snapshot joystick
sleep 12
snapshot settled
