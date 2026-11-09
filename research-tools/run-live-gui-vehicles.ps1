# For each simulator below: start it, start the research copy of Mission Planner 1.3.83, connect over TCP, open SETUP and look for a "Motor Test" menu entry; if it is there,
# open it, save a screenshot and the visible texts, and for Copter frames press "Test all in Sequence" with BM_CLICK while an independent observer records SERVO_OUTPUT_RAW
# (compared afterwards with the sweep). Output: sitl-evidence/live-gui-vehicles/. Simulator only, never a real vehicle. Real window, driven by a script, not a person.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$project = Split-Path -Parent $repo
$iso = Join-Path $project 'mission-planner-isolated'
$g = Join-Path $PSScriptRoot 'gui-driver.ps1'
$out = Join-Path $repo 'sitl-evidence\live-gui-vehicles'
New-Item -ItemType Directory -Force $out | Out-Null
$rw = '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload'
wsl.exe -d Ubuntu-E -e cp "$rw/research-tools/frame-page-sitl.sh" /home/think/frame-page-sitl.sh
wsl.exe -d Ubuntu-E -e cp "$rw/research-tools/sitl-servo-observer.py" /home/think/sitl-servo-observer.py
wsl.exe -d Ubuntu-E -e cp "$rw/research-tools/servo-observer-run.sh" /home/think/servo-observer-run.sh

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
function TextHandle([string]$text) {
    $l = Tree '' | Where-Object { $_ -match ('\| "\s*' + [regex]::Escape($text) + '\s*" \|') -and $_ -notmatch 'BUTTON' } | Select-Object -First 1
    if ($l) { return ($l -split ' \| ')[0] } else { return $null }
}
function ClickText([string]$text) { $h = TextHandle $text; if ($h) { & $g hwndclick $h 10 10 | Out-Null; return $true } else { return $false } }
function DismissDialogs {
    $main = (Windows | Where-Object { $_.Title -like 'Mission Planner 1.3*' } | Select-Object -First 1).Handle
    $seen = @()
    for ($round = 0; $round -lt 3; $round++) {
        $extra = Windows | Where-Object { $_.Handle -ne $main -and $_.Title -notlike 'Mission Planner 1.3*' }
        if (-not $extra) { break }
        foreach ($e in $extra) {
            $texts = (Tree $e.Title | Where-Object { $_ -match 'STATIC' } | ForEach-Object { (($_ -split ' \| ')[2]).Trim('"') } | Where-Object { $_ }) -join ' / '
            $seen += "[$($e.Title)] $texts"
            $btn = $null
            foreach ($t in @('OK', 'No', 'Cancel', 'Close')) { $btn = ButtonHandle $e.Title $t; if ($btn) { break } }
            if ($btn) { & $g bmclick $btn | Out-Null }
        }
        Start-Sleep -Seconds 2
    }
    return ($seen -join ' || ')
}

# model, binary, label, number of motor-test sequences to wait for (0 = do not press), sweep frame name for the comparison
$sims = @(
    @('hexa', 'arducopter', 'copter-hexa', 6, 'hexa'), @('octa', 'arducopter', 'copter-octa', 8, 'octa'), @('y6', 'arducopter', 'copter-y6', 6, 'y6'), @('tri', 'arducopter', 'copter-tri', 4, 'tri'),
    @('singlecopter', 'arducopter', 'copter-single', 0, ''), @('vectored', 'ardusub', 'sub-vectored', 0, ''), @('rover', 'ardurover', 'rover', 0, ''), @('quadplane', 'arduplane', 'quadplane', 0, '')
)
$summary = New-Object System.Text.StringBuilder
[void]$summary.AppendLine('label,connected_title,setup_menu_motor_test_entry,dialogs,motor_test_page_texts,buttons_named_test_motor,sequence_result')
foreach ($s in $sims) {
    $model = $s[0]; $bin = $s[1]; $label = $s[2]; $nseq = $s[3]; $sweepFrame = $s[4]
    Write-Output "=== $label"
    Get-Process -Name MissionPlanner -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
    wsl.exe -d Ubuntu-E -e pkill -f build/sitl/bin
    Start-Sleep -Seconds 2
    $sitl = Start-Process -FilePath wsl.exe -ArgumentList @('-d', 'Ubuntu-E', '-e', 'bash', '/home/think/frame-page-sitl.sh', 'run', $model, $bin, 'lv-sitl') -WindowStyle Hidden -PassThru
    wsl.exe -d Ubuntu-E -e bash /home/think/frame-page-sitl.sh wait lv-sitl | Out-Null
    $mp = Start-Process -FilePath "$iso\MissionPlanner.exe" -WorkingDirectory $iso -PassThru
    Start-Sleep -Seconds 30
    $tree = Tree ''
    $portCombo = (($tree | Where-Object { $_ -match 'COMBOBOX' -and $_ -match 'client \(15\d\d,0\)' } | Select-Object -First 1) -split ' \| ')[0]
    $strip = (($tree | Where-Object { $_ -match '"menuStrip1"' } | Select-Object -First 1) -split ' \| ')[0]
    & $g activate | Out-Null
    & $g hwndcombo $portCombo 'TCP' | Out-Null
    Start-Sleep -Seconds 1
    & $g hwndclick $strip 1772 19 | Out-Null
    foreach ($dlg in @('remote host', 'remote Port')) {
        if (-not (WaitWindow $dlg 20)) { throw "dialog not shown: $dlg ($label)" }
        & $g bmclick (ButtonHandle $dlg 'OK') | Out-Null
        Start-Sleep -Seconds 1
    }
    $conn = WaitWindow 'Mission Planner 1.3.83 build 1.3.9384.38258 Ardu' 150
    if (-not $conn) { $conn = WaitWindow 'Mission Planner 1.3.83 build 1.3.9384.38258 Rover' 5 }
    $title = (Windows | Where-Object { $_.Title -like 'Mission Planner 1.3*' } | Select-Object -First 1).Title
    Start-Sleep -Seconds 8
    $dialogs = DismissDialogs
    & $g hwndclick $strip 121 19 | Out-Null            # SETUP
    Start-Sleep -Seconds 4
    $dialogs += (DismissDialogs)
    $null = ClickText 'Optional Hardware'
    Start-Sleep -Seconds 2
    $hasMotorTest = [bool](TextHandle 'Motor Test')
    $pageTexts = ''; $btns = 0; $seq = 'not pressed'
    if (-not $hasMotorTest) { $null = ClickText '>> Optional Hardware'; Start-Sleep -Seconds 2; $hasMotorTest = [bool](TextHandle 'Motor Test') }
    if ($hasMotorTest) {
        $null = ClickText 'Motor Test'
        Start-Sleep -Seconds 4
        $dialogs += (DismissDialogs)
        & $g shot (Join-Path $out ("$label-motor-test.png")) | Out-Null
        $vis = Tree '' | Where-Object { $_ -match 'visible=True' }
        $vis | Set-Content -Path (Join-Path $out "$label-motor-test-controls.txt") -Encoding ascii
        $btns = @($vis | Where-Object { $_ -match '"Test motor ' }).Count
        $pageTexts = (($vis | Where-Object { $_ -match 'Motor Number|Class:|Type:' } | ForEach-Object { (($_ -split ' \| ')[2]).Trim('"') }) -join ' / ')
        if ($nseq -gt 0) {
            $obs = Start-Process -FilePath wsl.exe -ArgumentList @('-d', 'Ubuntu-E', '-e', 'bash', '/home/think/servo-observer-run.sh') -WindowStyle Hidden -PassThru
            Start-Sleep -Seconds 8
            $log = New-Object System.Text.StringBuilder
            [void]$log.AppendLine(('{0} ACTION-START sequence' -f [DateTime]::UtcNow.ToString('o')))
            $h = ButtonHandle '' 'Test all in Sequence'
            & $g bmclick $h | Out-Null
            Start-Sleep -Seconds ($nseq * 3 + 4)
            [void]$log.AppendLine(('{0} ACTION-END sequence' -f [DateTime]::UtcNow.ToString('o')))
            Set-Content -Path (Join-Path $out "$label-log.txt") -Value $log.ToString() -Encoding ascii
            $obs.WaitForExit(120000) | Out-Null
            wsl.exe -d Ubuntu-E -e cp /home/think/servo-observer.csv "$rw/sitl-evidence/live-gui-vehicles/$label-servo-observer.csv"
            $seq = (python -I (Join-Path $PSScriptRoot 'analyze-gui-sequence-generic.py') $out $label $sweepFrame) -join ' '
        }
    } else {
        & $g shot (Join-Path $out ("$label-setup-menu.png")) | Out-Null
        (Tree '' | Where-Object { $_ -match 'visible=True' }) | Set-Content -Path (Join-Path $out "$label-setup-menu-controls.txt") -Encoding ascii
    }
    [void]$summary.AppendLine(('{0},"{1}",{2},"{3}","{4}",{5},"{6}"' -f $label, ($title -replace '"', "'"), $hasMotorTest, ($dialogs -replace '"', "'"), ($pageTexts -replace '"', "'"), $btns, ($seq -replace '"', "'")))
    Write-Output ('{0}: motor test entry={1} buttons={2} {3}' -f $label, $hasMotorTest, $btns, $seq)
    Get-Process -Name MissionPlanner -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
    wsl.exe -d Ubuntu-E -e bash /home/think/frame-page-sitl.sh stop lv-sitl "$rw/sitl-evidence/live-gui-vehicles" "sitl-$label.log" | Out-Null
}
Set-Content -Path (Join-Path $out 'vehicles-summary.csv') -Value $summary.ToString() -Encoding ascii
