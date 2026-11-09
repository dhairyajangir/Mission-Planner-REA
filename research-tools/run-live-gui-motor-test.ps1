# With the research copy of Mission Planner 1.3.83 already connected to a disposable Copter simulator and showing the Motor Test page (see gui-driver.ps1 and
# sitl-evidence/live-gui-driven/), press "Test motor A", "Test motor B" and "Test all in Sequence" in the real window with window messages, while an independent
# pymavlink observer on SERIAL1 records SERVO_OUTPUT_RAW. Writes an action log in the format analyze-motor-buttons.py reads. Simulator only.
# The buttons are found by their text in the window's child-window list (gui-driver.ps1 tree) and clicked by handle with BM_CLICK (an earlier version posted mouse messages instead, which the buttons did not act on; see sitl-evidence/live-gui-driven-run2-mouse-messages-no-effect/).
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$g = Join-Path $PSScriptRoot 'gui-driver.ps1'
$out = Join-Path $repo 'sitl-evidence\live-gui-driven'
$rw = '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload'
wsl.exe -d Ubuntu-E -e cp "$rw/research-tools/sitl-servo-observer.py" /home/think/sitl-servo-observer.py
wsl.exe -d Ubuntu-E -e cp "$rw/research-tools/servo-observer-run.sh" /home/think/servo-observer-run.sh
$obs = Start-Process -FilePath wsl.exe -ArgumentList @('-d', 'Ubuntu-E', '-e', 'bash', '/home/think/servo-observer-run.sh') -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 6
$log = New-Object System.Text.StringBuilder
function Stamp([string]$kind, [string]$name) { [void]$log.AppendLine(('{0} ACTION-{1} {2}' -f [DateTime]::UtcNow.ToString('o'), $kind, $name)) }
function Handle([string]$text) {
    $line = (& $g tree | Where-Object { $_ -match ('BUTTON.app.0.37a0697_r6_ad1 \| "' + [regex]::Escape($text) + '"') } | Select-Object -First 1)
    if (-not $line) { throw "button not found: $text" }
    return ($line -split ' \| ')[0]
}
function Press([string]$name, [string]$buttonText, [int]$waitSeconds) {
    $h = Handle $buttonText
    Stamp 'START' $name
    & $g bmclick $h | Out-Null
    Start-Sleep -Seconds $waitSeconds
    Stamp 'END' $name
    & $g shot (Join-Path $out ("10-after-" + $name + ".png")) | Out-Null
}
Start-Sleep -Seconds 4                                   # quiet period so the observer sees the idle outputs
Press 'gui-test-motor-A' 'Test motor A' 5
Press 'gui-test-motor-B' 'Test motor B' 5
Press 'gui-test-all-in-sequence' 'Test all in Sequence' 16
Press 'gui-stop-all-motors' 'Stop all motors' 4
$obs.WaitForExit(120000) | Out-Null
Set-Content -Path (Join-Path $out 'gui-motor-test-log.txt') -Value $log.ToString() -Encoding ascii
wsl.exe -d Ubuntu-E -e cp /home/think/servo-observer.csv "$rw/sitl-evidence/live-gui-driven/gui-motor-test-servo-observer.csv"
wsl.exe -d Ubuntu-E -e cp /home/think/servo-observer.csv.statustext.txt "$rw/sitl-evidence/live-gui-driven/gui-motor-test-statustext.txt"
python -I (Join-Path $PSScriptRoot 'analyze-motor-buttons.py') $out 'gui-motor-test' (Join-Path $out 'gui-motor-test-summary.csv')
