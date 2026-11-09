# In the REAL window of the research copy of Mission Planner 1.3.83 (connected over TCP to a disposable Copter simulator, driven with window messages), open
# SETUP > Mandatory Hardware > Frame Type, choose the Hexa class picture and then the "X" type radio button, and after each step read FRAME_CLASS and FRAME_TYPE from the
# vehicle on SERIAL1 (tcp 5762) with an independent pymavlink client. Records dialogs the page raises. Simulator only, never a real vehicle.
# Output: sitl-evidence/live-gui-frame-change/.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$project = Split-Path -Parent $repo
$iso = Join-Path $project 'mission-planner-isolated'
$g = Join-Path $PSScriptRoot 'gui-driver.ps1'
$out = Join-Path $repo 'sitl-evidence\live-gui-frame-change'
New-Item -ItemType Directory -Force $out | Out-Null
$rw = '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload'
Get-Process -Name MissionPlanner -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
wsl.exe -d Ubuntu-E -e pkill -f build/sitl/bin
Start-Sleep -Seconds 2
wsl.exe -d Ubuntu-E -e cp "$rw/research-tools/frame-page-sitl.sh" /home/think/frame-page-sitl.sh
wsl.exe -d Ubuntu-E -e cp "$rw/research-tools/sitl-param-presence.py" /home/think/sitl-param-presence.py
$sitl = Start-Process -FilePath wsl.exe -ArgumentList @('-d', 'Ubuntu-E', '-e', 'bash', '/home/think/frame-page-sitl.sh', 'run', '+', 'arducopter', 'fc-sitl') -WindowStyle Hidden -PassThru
wsl.exe -d Ubuntu-E -e bash /home/think/frame-page-sitl.sh wait fc-sitl
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
    $r = wsl.exe -d Ubuntu-E -e bash -c "source ~/venv-ap/bin/activate; python3 ~/sitl-param-presence.py 5762 FRAME_CLASS FRAME_TYPE" 2>&1
    $line = "$label :: " + (($r | Where-Object { $_ -match 'FRAME_' }) -join ' ; ')
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
& $g click 62 122 | Out-Null                        # Frame Type
Start-Sleep -Seconds 4
& $g shot (Join-Path $out '01-frame-type-before.png') | Out-Null
DismissDialogs 'opening Frame Type'

# class pictures are at window y 135, x 226 (Undefined) 306 (Quad) 386 (Hexa) 466 (Octa) 546 (OctaQuad) 626 (Y6) 706 (Heli) 786 (Tri); client = window minus (8, 31)
& $g bmclickat 378 104 | Out-Null                   # Hexa
Start-Sleep -Seconds 4
DismissDialogs 'after choosing Hexa'
& $g shot (Join-Path $out '02-after-hexa.png') | Out-Null
VehicleFrame 'after choosing the Hexa class picture'

# "X, Y6A" type radio at window (251, 311)
& $g bmclickat 243 280 | Out-Null
Start-Sleep -Seconds 4
DismissDialogs 'after choosing X'
& $g shot (Join-Path $out '03-after-x.png') | Out-Null
VehicleFrame 'after choosing the X type radio'

Get-Process -Name MissionPlanner -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
wsl.exe -d Ubuntu-E -e bash /home/think/frame-page-sitl.sh stop fc-sitl "$rw/sitl-evidence/live-gui-frame-change" sitl.log
Get-Content (Join-Path $out 'vehicle-frame-readings.txt')
if (Test-Path (Join-Path $out 'dialogs.txt')) { Get-Content (Join-Path $out 'dialogs.txt') }
