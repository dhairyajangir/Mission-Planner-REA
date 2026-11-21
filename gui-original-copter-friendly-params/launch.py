"""Launch the same private guest with bounded retries for a changing X window tree."""
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
launcher = REPO / "research-tools/observe-original-copter-sensors.sh"
capture = (REPO / "gui-original-copter-sensors/capture.sh").read_text()
original = '    xwininfo -root -tree > "/evidence/windows-$1.txt"\n    xwd -silent -root -out "/evidence/screen-$1.xwd"'
replacement = '''    local label=$1
    if [[ "$label" == extended || "$label" == extended-settled ]]; then sleep 16; fi
    local index
    for index in {1..12}; do
        if xwininfo -root -tree > "/evidence/windows-$label.tmp"; then
            mv "/evidence/windows-$label.tmp" "/evidence/windows-$label.txt"
            xwd -silent -root -out "/evidence/screen-$label.xwd"
            return 0
        fi
        echo "Retrying window-tree capture $label ($index/12)"
        sleep 2
    done
    echo "Window tree unavailable for $label"
    xwd -silent -root -out "/evidence/screen-$label.xwd"'''
assert capture.count(original) == 1
capture = capture.replace(original, replacement).replace("mono MissionPlanner.exe", "mono --interp MissionPlanner.exe")
script = launcher.read_text()
copy = 'cp "$evidence/capture.sh" "$out/capture.sh"'
assert script.count(copy) == 1
script = script.replace(copy, 'cat >"$out/capture.sh" <<\'GUEST_CAPTURE\'\n' + capture + '\nGUEST_CAPTURE')
subprocess.run(["bash", "-c", script, str(launcher), "--copter"], check=True)
