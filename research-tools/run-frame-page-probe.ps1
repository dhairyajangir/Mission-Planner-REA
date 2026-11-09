# Build PageFrameProbe.cs and drive the original ConfigFrameClassType page against disposable ArduCopter SITLs of several frames (Ubuntu-E).
# Part 1: page state for each frame (what the page shows next to the vehicle's FRAME_CLASS and FRAME_TYPE).
# Part 2: change the class and type through the page, restart the simulator without wiping its parameters, and motor-test the new frame.
# Output: sitl-evidence/frame-page/. Simulator only, never a real vehicle.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$project = Split-Path -Parent $repo
$isolated = Join-Path $project 'mission-planner-isolated'
$out = Join-Path $repo 'sitl-evidence\frame-page'
$bin = Join-Path $env:TEMP 'frame-page-probe'
New-Item -ItemType Directory -Force $out, $bin | Out-Null
$csc = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
& $csc /nologo /target:exe /out:"$bin\PageFrameProbe.exe" /r:System.Windows.Forms.dll /r:System.Drawing.dll "$repo\research-tools\PageFrameProbe.cs"
if ($LASTEXITCODE -ne 0) { throw "compile failed" }
$shSrc = '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload/research-tools/frame-page-sitl.sh'
wsl.exe -d Ubuntu-E -e cp $shSrc /home/think/frame-page-sitl.sh
$evWsl = '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload/sitl-evidence/frame-page'

function Start-Frame($model, $binary, $work, $nowipe) {
    $argsList = @('-d', 'Ubuntu-E', '-e', 'bash', '/home/think/frame-page-sitl.sh', 'run', $model, $binary, $work)
    if ($nowipe) { $argsList += 'nowipe' }
    $p = Start-Process -FilePath wsl.exe -ArgumentList $argsList -WindowStyle Hidden -PassThru
    wsl.exe -d Ubuntu-E -e bash /home/think/frame-page-sitl.sh wait $work
    Start-Sleep -Seconds 10
    $c = New-Object System.Net.Sockets.TcpClient('127.0.0.1', 5760)     # priming client, as in the earlier probes
    $s = $c.GetStream(); $s.ReadTimeout = 15000
    $buf = New-Object byte[] 512
    $n = $s.Read($buf, 0, 512)
    Write-Output "prime: simulator sent $n bytes"
    $c.Close()
    Start-Sleep -Seconds 3
    return $p
}

function Stop-Frame($p, $work, $logName) {
    wsl.exe -d Ubuntu-E -e bash /home/think/frame-page-sitl.sh stop $work $evWsl $logName
    if ($p -and -not $p.HasExited) { $p.Kill() }
}

# Part 1: state only. model, binary, label
$state = @(
    @('+', 'arducopter', 'quad-plus'), @('X', 'arducopter', 'quad-x'), @('hexa', 'arducopter', 'hexa'), @('octa', 'arducopter', 'octa'),
    @('octa-quad', 'arducopter', 'octa-quad'), @('y6', 'arducopter', 'y6'), @('tri', 'arducopter', 'tri'), @('deca', 'arducopter', 'deca'),
    @('singlecopter', 'arducopter', 'singlecopter'), @('heli', 'arducopter-heli', 'heli')
)
foreach ($f in $state) {
    Write-Output "=== state: $($f[2])"
    $p = Start-Frame $f[0] $f[1] 'fp-sitl' $false
    try { & "$bin\PageFrameProbe.exe" $isolated $out 5760 "state-$($f[2]).txt" | Out-Null } finally { Stop-Frame $p 'fp-sitl' "sitl-state-$($f[2]).log" }
}

# Part 2: change through the page, then restart and motor-test
Write-Output "=== change: quad-plus -> hexa -> X through the page"
$p = Start-Frame '+' 'arducopter' 'fp-change' $false
try { & "$bin\PageFrameProbe.exe" $isolated $out 5760 'change-quad-to-hexa-x.txt' radioButtonHexa radioButton_X | Out-Null } finally { Stop-Frame $p 'fp-change' 'sitl-change-1.log' }
Write-Output "=== restart without wiping parameters and motor-test the frame the page set"
wsl.exe -d Ubuntu-E -e cp '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload/research-tools/run-restart-sweep.sh' /home/think/run-restart-sweep.sh
wsl.exe -d Ubuntu-E -e bash /home/think/run-restart-sweep.sh
