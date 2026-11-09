# (script copied from run-live-gui-flight-modes.ps1; steps below replaced) In the REAL window of the research copy of Mission Planner 1.3.83 (connected over TCP to a disposable Copter simulator, driven with window messages), open SETUP > Mandatory Hardware > Flight Modes, choose Loiter for flight mode 1 and Alt Hold for flight mode 2, press Save Modes, and read FLTMODE1 to FLTMODE6 from the vehicle on SERIAL1 before and after with an independent pymavlink client. (This header replaces the one copied from the frame-change script.)
# (copied header) open
# SETUP > Mandatory Hardware > Frame Type, choose the Hexa class picture and then the "X" type radio button, and after each step read FRAME_CLASS and FRAME_TYPE from the
# vehicle on SERIAL1 (tcp 5762) with an independent pymavlink client. Records dialogs the page raises. Simulator only, never a real vehicle.
# Output: sitl-evidence/live-gui-frame-change/.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$project = Split-Path -Parent $repo
$iso = Join-Path $project 'mission-planner-isolated'
$g = Join-Path $PSScriptRoot 'gui-driver.ps1'
$out = Join-Path $repo 'sitl-evidence\live-gui-servo-reverse'
New-Item -ItemType Directory -Force $out | Out-Null
$rw = '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload'
Get-Process -Name MissionPlanner -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
wsl.exe -d Ubuntu-E -e pkill -f build/sitl/bin
Start-Sleep -Seconds 2
wsl.exe -d Ubuntu-E -e cp "$rw/research-tools/frame-page-sitl.sh" /home/think/frame-page-sitl.sh
wsl.exe -d Ubuntu-E -e cp "$rw/research-tools/sitl-param-presence.py" /home/think/sitl-param-presence.py
$sitl = Start-Process -FilePath wsl.exe -ArgumentList @('-d', 'Ubuntu-E', '-e', 'bash', '/home/think/frame-page-sitl.sh', 'run', '+', 'arducopter', 'sr-sitl') -WindowStyle Hidden -PassThru
wsl.exe -d Ubuntu-E -e bash /home/think/frame-page-sitl.sh wait sr-sitl
$mp = Start-Process -FilePath "$iso\MissionPlanner.exe" -WorkingDirectory $iso -PassThru
Start-Sleep -Seconds 30
function Windows { (& $g list) | ForEach-Object { $p = $_ -split ' \| '; [pscustomobject]@{ Handle = $p[0]; Title = $p[1] } } }
function Tree([string]$title) { if ($title) { & $g tree $title } else { & $g tree } }
function ButtonHandle([string]$windowTitle, [string]$text) {
    $l = Tree $windowTitle | Where-Object { $_ -match ('BUTTON\.app\.0\.37a0697_r6_ad1 \| "' + [regex]::Escape($text) + '"') } | Select-Object -First 1
    if ($l) { return ($l -split ' \| ')[0] } else { return $null }
}
function WaitWindow([string]$contains, [int]$seconds) {
    for ($i = 0; $i -lt $seconds; $i++) { $w = Windows | Where-Object { $_.Title -like "*$contains*" } | Select-Object -First 1; if ($w) { return $w }; Start-Sleep -Seconds 1 }
    return $null
}
function VehicleFrame([string]$label) {
    $r = wsl.exe -d Ubuntu-E -e bash -c "source ~/venv-ap/bin/activate; python3 ~/sitl-param-presence.py 5762 SERVO1_REVERSED SERVO2_REVERSED SERVO3_REVERSED SERVO4_REVERSED" 2>&1
    $line = "$label :: " + (($r | Where-Object { $_ -match 'SERVO' }) -join ' ; ')
    Add-Content -Path (Join-Path $out 'vehicle-frame-readings.txt') -Value $line -Encoding ascii
    $line
}
function DismissDialogs([string]$step) {
    $main = (Windows | Where-Object { $_.Title -like 'Mission Planner 1.3*' } | Select-Object -First 1).Handle
    for ($round = 0; $round -lt 4; $round++) {
        $extra = Windows | Where-Object { $_.Handle -ne $main -and $_.Title -notlike 'Mission Planner 1.3*' }
        if (-not $extra) { break }
        foreach ($e in $extra) {
            $texts = (Tree $e.Title | Where-Object { $_ -match 'STATIC' } | ForEach-Object { (($_ -split ' \| ')[2]).Trim('"') } | Where-Object { $_ }) -join ' / '
            Add-Content -Path (Join-Path $out 'dialogs.txt') -Value ("$step :: [$($e.Title)] $texts") -Encoding ascii
            $btn = $null
            foreach ($t in @('OK', 'No', 'Cancel', 'Close')) { $btn = ButtonHandle $e.Title $t; if ($btn) { break } }
            if ($btn) { & $g bmclick $btn | Out-Null }
        }
        Start-Sleep -Seconds 2
    }
}
Remove-Item (Join-Path $out 'vehicle-frame-readings.txt'), (Join-Path $out 'dialogs.txt') -ErrorAction SilentlyContinue

$tree = Tree ''
$portCombo = (($tree | Where-Object { $_ -match 'COMBOBOX' -and $_ -match 'client \(15\d\d,0\)' } | Select-Object -First 1) -split ' \| ')[0]
$strip = (($tree | Where-Object { $_ -match '"menuStrip1"' } | Select-Object -First 1) -split ' \| ')[0]
& $g activate | Out-Null
& $g hwndcombo $portCombo 'TCP' | Out-Null
Start-Sleep -Seconds 1
& $g hwndclick $strip 1772 19 | Out-Null
foreach ($dlg in @('remote host', 'remote Port')) {
    if (-not (WaitWindow $dlg 20)) { throw "dialog not shown: $dlg" }
    & $g bmclick (ButtonHandle $dlg 'OK') | Out-Null
    Start-Sleep -Seconds 1
}
if (-not (WaitWindow 'ArduCopter' 120)) { throw 'did not connect' }
Start-Sleep -Seconds 8
VehicleFrame 'before any GUI action'

& $g hwndclick $strip 121 19 | Out-Null            # SETUP
Start-Sleep -Seconds 3
& $g click 87 92 | Out-Null                         # Mandatory Hardware
Start-Sleep -Seconds 2
$so = $null
foreach ($i in 1..3) { $h = (Tree '' | Where-Object { $_ -match '\| "\s*Servo Output\s*" \|' -and $_ -notmatch 'BUTTON' } | Select-Object -First 1); if ($h) { $so = ($h -split ' \| ')[0]; break }; Start-Sleep -Seconds 1 }
if (-not $so) { throw 'Servo Output menu entry not found' }
& $g hwndclick $so 10 10 | Out-Null
Start-Sleep -Seconds 5
DismissDialogs 'opening Servo Output'
& $g shot (Join-Path $out '01-servo-output-before.png') | Out-Null
# the page has 16 unlabelled check boxes, one per servo row; the first by vertical position is the Reverse box of SERVO1
$boxes = @(Tree '' | Where-Object { $_ -match 'BUTTON' -and $_ -match '"" \|' -and $_ -match 'client \(\d+,\d+\) \d+x\d+' } | ForEach-Object { $p = $_ -split ' \| '; $m = [regex]::Match($p[3], 'client \((\d+),(\d+)\) (\d+)x(\d+)'); [pscustomobject]@{ H = $p[0]; X = [int]$m.Groups[1].Value; Y = [int]$m.Groups[2].Value; W = [int]$m.Groups[3].Value } } | Where-Object { $_.X -gt 180 -and $_.Y -gt 60 } | Sort-Object Y, X)
$boxes | ForEach-Object { Add-Content -Path (Join-Path $out 'checkbox-candidates.txt') -Value ("handle {0} client ({1},{2}) width {3}" -f $_.H, $_.X, $_.Y, $_.W) -Encoding ascii }
if ($boxes.Count -lt 16) { throw "expected 16 check boxes, found $($boxes.Count)" }
$first = $boxes[0]
VehicleFrame 'before pressing the first Reverse box'
& $g bmclick $first.H | Out-Null
Start-Sleep -Seconds 4
DismissDialogs 'after the first press'
& $g shot (Join-Path $out '02-after-first-press.png') | Out-Null
VehicleFrame 'after the first press'
& $g bmclick $first.H | Out-Null
Start-Sleep -Seconds 4
DismissDialogs 'after the second press'
& $g shot (Join-Path $out '03-after-second-press.png') | Out-Null
VehicleFrame 'after the second press (restore)'

Get-Process -Name MissionPlanner -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
wsl.exe -d Ubuntu-E -e bash /home/think/frame-page-sitl.sh stop fc-sitl "$rw/sitl-evidence/live-gui-frame-change" sitl.log
Get-Content (Join-Path $out 'vehicle-frame-readings.txt')
if (Test-Path (Join-Path $out 'dialogs.txt')) { Get-Content (Join-Path $out 'dialogs.txt') }
