"""Retry the existing private guest with the release running in Mono's interpreter."""
from pathlib import Path
import subprocess

launcher = Path(__file__).resolve().parent.parent / "research-tools/observe-original-copter-sensors.sh"
script = launcher.read_text()
copy = 'cp "$evidence/capture.sh" "$out/capture.sh"'
assert script.count(copy) == 1
script = script.replace(copy, """sed 's/^mono MissionPlanner.exe/mono --interp MissionPlanner.exe/' "$evidence/capture.sh" >"$out/capture.sh"
grep -q '^mono --interp MissionPlanner.exe' "$out/capture.sh" """)
subprocess.run(["bash", "-c", script, str(launcher), "--copter"], check=True)
