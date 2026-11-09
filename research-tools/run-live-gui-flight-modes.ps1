# In the REAL window of the research copy of Mission Planner 1.3.83 (connected over TCP to a disposable Copter simulator, driven with window messages), open SETUP > Mandatory Hardware > Flight Modes, choose Loiter for flight mode 1 and Alt Hold for flight mode 2, press Save Modes, and read FLTMODE1 to FLTMODE6 from the vehicle on SERIAL1 before and after with an independent pymavlink client. (This header replaces the one copied from the frame-change script.)
# (copied header) open
# SETUP > Mandatory Hardware > Frame Type, choose the Hexa class picture and then the "X" type radio button, and after each step read FRAME_CLASS and FRAME_TYPE from the
# vehicle on SERIAL1 (tcp 5762) with an independent pymavlink client. Records dialogs the page raises. Simulator only, never a real vehicle.
# Output: sitl-evidence/live-gui-frame-change/.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$project = Split-Path -Parent $repo
$iso = Join-Path $project 'mission-planner-isolated'
$g = Join-Path $PSScriptRoot 'gui-driver.ps1'
$out = Join-Path $repo 'sitl-evidence\live-gui-flight-modes'
New-Item -ItemType Directory -Force $out | Out-Null
$rw = '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload'
Get-Process -Name MissionPlanner -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
wsl.exe -d Ubuntu-E -e pkill -f build/sitl/bin
Start-Sleep -Seconds 2
wsl.exe -d Ubuntu-E -e cp "$rw/research-tools/frame-page-sitl.sh" /home/think/frame-page-sitl.sh
wsl.exe -d Ubuntu-E -e cp "$rw/research-tools/sitl-param-presence.py" /home/think/sitl-param-presence.py
$sitl = Start-Process -FilePath wsl.exe -ArgumentList @('-d', 'Ubuntu-E', '-e', 'bash', '/home/think/frame-page-sitl.sh', 'run', '+', 'arducopter', 'fm-sitl') -WindowStyle Hidden -PassThru
wsl.exe -d Ubuntu-E -e bash /home/think/frame-page-sitl.sh wait fm-sitl
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
    $r = wsl.exe -d Ubuntu-E -e bash -c "source ~/venv-ap/bin/activate; python3 ~/sitl-param-presence.py 5762 FLTMODE1 FLTMODE2 FLTMODE3 FLTMODE4 FLTMODE5 FLTMODE6" 2>&1
    $line = "$label :: " + (($r | Where-Object { $_ -match 'FLTMODE' }) -join ' ; ')
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
$fm = $null
foreach ($i in 1..3) { $h = (Tree '' | Where-Object { $_ -match '\| "\s*Flight Modes\s*" \|' -and $_ -notmatch 'BUTTON' } | Select-Object -First 1); if ($h) { $fm = ($h -split ' \| ')[0]; break }; Start-Sleep -Seconds 1 }
if (-not $fm) { throw 'Flight Modes menu entry not found' }
& $g hwndclick $fm 10 10 | Out-Null
Start-Sleep -Seconds 4
DismissDialogs 'opening Flight Modes'
& $g shot (Join-Path $out '01-flight-modes-before.png') | Out-Null
$combos = @(Tree '' | Where-Object { $_ -match 'COMBOBOX' -and $_ -match 'client \(285,\d+\)' } | ForEach-Object { $p = $_ -split ' \| '; $y = [int](([regex]::Match($p[3], 'client \((\d+),(\d+)\)').Groups[2].Value)); [pscustomobject]@{ H = $p[0]; Y = $y } } | Sort-Object Y)
$combos | ForEach-Object { Add-Content -Path (Join-Path $out 'flight-mode-combos.txt') -Value ("handle {0} client y {1}" -f $_.H, $_.Y) -Encoding ascii }
if ($combos.Count -lt 6) { throw "expected 6 flight mode combos, found $($combos.Count)" }
& $g hwndcombo $combos[0].H 'Loiter' | Out-Null
Start-Sleep -Seconds 1
& $g hwndcombo $combos[1].H 'Alt' | Out-Null
Start-Sleep -Seconds 1
& $g shot (Join-Path $out '02-modes-chosen-before-save.png') | Out-Null
VehicleFrame 'after choosing in the combo boxes, before Save Modes'
$save = ButtonHandle '' 'Save Modes'
& $g bmclick $save | Out-Null
Start-Sleep -Seconds 5
DismissDialogs 'after Save Modes'
& $g shot (Join-Path $out '03-after-save.png') | Out-Null
VehicleFrame 'after pressing Save Modes'

Get-Process -Name MissionPlanner -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
wsl.exe -d Ubuntu-E -e bash /home/think/frame-page-sitl.sh stop fc-sitl "$rw/sitl-evidence/live-gui-frame-change" sitl.log
Get-Content (Join-Path $out 'vehicle-frame-readings.txt')
if (Test-Path (Join-Path $out 'dialogs.txt')) { Get-Content (Join-Path $out 'dialogs.txt') }
