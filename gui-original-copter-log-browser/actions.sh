sha256sum /evidence/downloaded.bin
for ((step=1;step<=64;step++)); do
    for ((poll=0;poll<600;poll++)); do
        [[ -s "/evidence/action-$step" ]] && break
        kill -0 "$app_pid" 2>/dev/null || exit 2
        sleep 1
    done
    [[ -s "/evidence/action-$step" ]] || break
    read -r action x y label < "/evidence/action-$step"
    [[ "$label" =~ ^[a-z0-9-]+$ && "$x" =~ ^[0-9]+$ && "$y" =~ ^[0-9]+$ ]]
    echo "$(date -u +%FT%TZ) $step $action $x $y $label"
    case "$action" in
        done) break ;;
        click) xdotool mousemove "$x" "$y" click 1 ;;
        repeat) xdotool mousemove "$x" "$y" click --repeat 8 1 ;;
        double) xdotool mousemove "$x" "$y" click --repeat 2 1 ;;
        filename) xdotool key ctrl+a; xdotool type '/evidence/downloaded.bin' ;;
        enter) xdotool key Return ;;
        right) xdotool key Right ;;
        home) xdotool key Home ;;
        down) xdotool key Down ;;
        up) xdotool key Up ;;
        gps) xdotool type 'GPS' ;;
        space) xdotool key space ;;
        wheel) xdotool mousemove "$x" "$y" click --repeat 3 5 ;;
        observe) true ;;
        *) exit 2 ;;
    esac
    sleep 2
    snapshot "$label"
done
