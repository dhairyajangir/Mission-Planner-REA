for ((step=1;step<=25;step++)); do
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
        ctrlf) xdotool key ctrl+f ;;
        waittools)
            for ((i=0;i<120;i++)); do
                if xdotool search --onlyvisible --name '^Create custom audio warnings$' >/dev/null; then break; fi
                sleep 1
            done
            sleep 3 ;;
        showmanager)
            button=$(xdotool search --onlyvisible --name '^Warning Manager$')
            [[ "$button" =~ ^[0-9]+$ ]]
            xdotool mousemove --window "$button" 40 6 click 1 ;;
        redrawmanager)
            # Only the top-level dialog has this title and includes its sibling controls.
            window=$(xdotool search --onlyvisible --maxdepth 1 --name '^Warning Manager$')
            [[ "$window" =~ ^[0-9]+$ ]]
            xdotool windowsize "$window" 890 260
            sleep 2
            xdotool mousemove 1130 700 ;;
        escape) xdotool key Escape ;;
        scroll) xdotool mousemove "$x" "$y" click --repeat 3 5 ;;
        observe) true ;;
        *) exit 2 ;;
    esac
    sleep 3
    snapshot "$label"
done
