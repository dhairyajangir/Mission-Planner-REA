# Open every page of the SETUP menu (Mandatory Hardware and Optional Hardware, not Install Firmware and not Advanced) in the REAL window of the research copy of
# Mission Planner 1.3.83, connected over TCP to a disposable Copter simulator, driven with window messages by gui-driver.ps1. For each page: click the menu entry, wait 3 s,
# record any dialog the page opened (title and texts, then dismiss it with OK, else No, else Cancel, else the first button), save a screenshot (JPEG) and the list of visible
# child windows with text and enabled state, and count the visible controls by kind. Output: sitl-evidence/live-gui-pages/. Simulator only, never a real vehicle.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$project = Split-Path -Parent $repo
$iso = Join-Path $project 'mission-planner-isolated'
$g = Join-Path $PSScriptRoot 'gui-driver.ps1'
$out = Join-Path $repo 'sitl-evidence\live-gui-pages'
New-Item -ItemType Directory -Force $out | Out-Null
$rw = '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload'

Get-Process -Name MissionPlanner -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
wsl.exe -d Ubuntu-E -e pkill -f build/sitl/bin
Start-Sleep -Seconds 2
wsl.exe -d Ubuntu-E -e cp "$rw/research-tools/frame-page-sitl.sh" /home/think/frame-page-sitl.sh
$sitl = Start-Process -FilePath wsl.exe -ArgumentList @('-d', 'Ubuntu-E', '-e', 'bash', '/home/think/frame-page-sitl.sh', 'run', '+', 'arducopter', 'pages-sitl') -WindowStyle Hidden -PassThru
wsl.exe -d Ubuntu-E -e bash /home/think/frame-page-sitl.sh wait pages-sitl
$mp = Start-Process -FilePath "$iso\MissionPlanner.exe" -WorkingDirectory $iso -PassThru
Start-Sleep -Seconds 30

function Windows { (& $g list) | ForEach-Object { $p = $_ -split ' \| '; [pscustomobject]@{ Handle = $p[0]; Title = $p[1]; Size = $p[3] } } }
function Tree([string]$title) { if ($title) { & $g tree $title } else { & $g tree } }
function ButtonHandle([string]$windowTitle, [string]$text) {
    $l = Tree $windowTitle | Where-Object { $_ -match ('BUTTON\.app\.0\.37a0697_r6_ad1 \| "' + [regex]::Escape($text) + '"') } | Select-Object -First 1
    if ($l) { return ($l -split ' \| ')[0] } else { return $null }
}
function WaitWindow([string]$contains, [int]$seconds) {
    for ($i = 0; $i -lt $seconds; $i++) { $w = Windows | Where-Object { $_.Title -like "*$contains*" } | Select-Object -First 1; if ($w) { return $w }; Start-Sleep -Seconds 1 }
    return $null
}

# connect: TCP in the port combo, CONNECT, then the host and port dialogs
$tree = Tree ''
$portCombo = (($tree | Where-Object { $_ -match 'COMBOBOX' -and $_ -match 'client \(15\d\d,0\)' } | Select-Object -First 1) -split ' \| ')[0]
$strip = (($tree | Where-Object { $_ -match '"menuStrip1"' } | Select-Object -First 1) -split ' \| ')[0]
& $g activate | Out-Null
& $g hwndcombo $portCombo 'TCP' | Out-Null
Start-Sleep -Seconds 1
& $g hwndclick $strip 1772 19 | Out-Null
foreach ($dlg in @('remote host', 'remote Port')) {
    $w = WaitWindow $dlg 20
    if (-not $w) { throw "dialog not shown: $dlg" }
    $ok = ButtonHandle $dlg 'OK'
    & $g bmclick $ok | Out-Null
    Start-Sleep -Seconds 1
}
$connected = WaitWindow 'ArduCopter' 120
if (-not $connected) { throw 'did not connect' }
Start-Sleep -Seconds 5
& $g shot (Join-Path $out '000-connected.jpg') | Out-Null

# SETUP, then expand both groups (window y 123 and 513 in the 1821x1219 window; client = window minus (8, 31))
& $g hwndclick $strip 121 19 | Out-Null
Start-Sleep -Seconds 3
& $g click 87 92 | Out-Null
Start-Sleep -Seconds 2
& $g click 82 482 | Out-Null
Start-Sleep -Seconds 2
& $g shot (Join-Path $out '001-setup-menu-expanded.jpg') | Out-Null

$pages = @(
    @('Frame Type', 153), @('Accel Calibration', 183), @('Compass', 213), @('Radio Calibration', 243), @('Servo Output', 273), @('Serial Ports', 303), @('ESC Calibration', 333),
    @('Flight Modes', 363), @('FailSafe', 393), @('Initial Tune Parameters', 423), @('HW ID', 453), @('ADSB', 483),
    @('RTK-GPS Inject', 543), @('CubeID Update', 573), @('Sik Radio', 603), @('CAN GPS Order', 633), @('Battery Monitor', 663), @('Battery Monitor 2', 693), @('DroneCAN-UAVCAN', 723),
    @('Joystick', 753), @('Compass-Motor Calibration', 783), @('Range Finder', 813), @('Airspeed', 843), @('PX4Flow', 873), @('Optical Flow', 903), @('OSD', 933), @('Camera Gimbal', 963),
    @('Motor Test', 993), @('Bluetooth Setup', 1023), @('Parachute', 1053), @('ESP8266 Setup', 1083), @('Antenna Tracker', 1113), @('FFT Setup', 1143)
)
$main = (Windows | Where-Object { $_.Title -like 'Mission Planner 1.3*' } | Select-Object -First 1).Handle
$csv = New-Object System.Text.StringBuilder
[void]$csv.AppendLine('page,dialogs_opened,visible_child_windows,visible_buttons,visible_edits,visible_combos,visible_static_texts,disabled_visible_controls,first_texts')
$n = 2
foreach ($pg in $pages) {
    $name = $pg[0]; $y = $pg[1]
    & $g click 72 ($y - 31) | Out-Null
    Start-Sleep -Seconds 3
    $dialogs = @()
    for ($round = 0; $round -lt 4; $round++) {
        $extra = Windows | Where-Object { $_.Handle -ne $main -and $_.Title -notlike 'Mission Planner 1.3*' }
        if (-not $extra) { break }
        foreach ($e in $extra) {
            $texts = (Tree $e.Title | Where-Object { $_ -match 'STATIC|EDIT' } | ForEach-Object { (($_ -split ' \| ')[2]).Trim('"') } | Where-Object { $_ } ) -join ' / '
            $dialogs += ('[{0}] {1}' -f $e.Title, $texts)
            $btn = $null
            foreach ($t in @('OK', 'No', 'Cancel', 'Close')) { $btn = ButtonHandle $e.Title $t; if ($btn) { break } }
            if (-not $btn) { $l = Tree $e.Title | Where-Object { $_ -match 'BUTTON' } | Select-Object -First 1; if ($l) { $btn = ($l -split ' \| ')[0] } }
            if ($btn) { & $g bmclick $btn | Out-Null }
        }
        Start-Sleep -Seconds 2
    }
    $safe = ('{0:D3}-{1}' -f $n, ($name -replace '[^A-Za-z0-9]+', '-'))
    & $g shot (Join-Path $out ($safe + '.jpg')) | Out-Null
    $vis = Tree '' | Where-Object { $_ -match 'visible=True' }
    $vis | Set-Content -Path (Join-Path $out ($safe + '-controls.txt')) -Encoding ascii
    $cnt = { param($pat) @($vis | Where-Object { $_ -match $pat }).Count }
    $btns = & $cnt 'BUTTON'; $edits = & $cnt 'EDIT'; $combos = & $cnt 'COMBOBOX'; $stat = & $cnt 'STATIC'
    $dis = @($vis | Where-Object { $_ -match 'enabled=False' }).Count
    $first = (($vis | Where-Object { $_ -match '\| "[^"]+" \|' } | Select-Object -First 6 | ForEach-Object { (($_ -split ' \| ')[2]).Trim('"') }) -join ' / ') -replace ',', ';'
    [void]$csv.AppendLine(('{0},"{1}",{2},{3},{4},{5},{6},{7},"{8}"' -f $name, (($dialogs -join ' || ') -replace '"', "'"), $vis.Count, $btns, $edits, $combos, $stat, $dis, $first))
    $n++
}
Set-Content -Path (Join-Path $out 'pages-summary.csv') -Value $csv.ToString() -Encoding ascii
Get-Process -Name MissionPlanner -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
wsl.exe -d Ubuntu-E -e bash /home/think/frame-page-sitl.sh stop pages-sitl "$rw/sitl-evidence/live-gui-pages" sitl.log
Get-Content (Join-Path $out 'pages-summary.csv') | Select-Object -First 40
