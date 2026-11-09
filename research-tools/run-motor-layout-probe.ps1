# Build PageMotorLayoutProbe.cs and list what the original ConfigMotorTest page draws (buttons and "Motor Number" labels) against disposable ArduCopter SITLs
# of several frames (Ubuntu-E). No test button is pressed. Output: sitl-evidence/motor-layout-page/. Simulator only, never a real vehicle.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$project = Split-Path -Parent $repo
$isolated = Join-Path $project 'mission-planner-isolated'
$out = Join-Path $repo 'sitl-evidence\motor-layout-page'
$bin = Join-Path $env:TEMP 'motor-layout-probe'
New-Item -ItemType Directory -Force $out, $bin | Out-Null
$csc = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
& $csc /nologo /target:exe /out:"$bin\PageMotorLayoutProbe.exe" /r:System.Windows.Forms.dll /r:System.Drawing.dll "$repo\research-tools\PageMotorLayoutProbe.cs"
if ($LASTEXITCODE -ne 0) { throw "compile failed" }
wsl.exe -d Ubuntu-E -e cp '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload/research-tools/frame-page-sitl.sh' /home/think/frame-page-sitl.sh
$evWsl = '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload/sitl-evidence/motor-layout-page'

function Start-Frame($model, $binary, $work) {
    $p = Start-Process -FilePath wsl.exe -ArgumentList @('-d', 'Ubuntu-E', '-e', 'bash', '/home/think/frame-page-sitl.sh', 'run', $model, $binary, $work) -WindowStyle Hidden -PassThru
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

$frames = @(
    @('+', 'arducopter', 'quad-plus'), @('X', 'arducopter', 'quad-x'), @('bfx', 'arducopter', 'quad-bfx'), @('hexa', 'arducopter', 'hexa'), @('hexax', 'arducopter', 'hexa-x'),
    @('octa', 'arducopter', 'octa'), @('octa-quad', 'arducopter', 'octa-quad'), @('y6', 'arducopter', 'y6'), @('tri', 'arducopter', 'tri'), @('deca', 'arducopter', 'deca'),
    @('dodeca-hexa', 'arducopter', 'dodeca-hexa'), @('singlecopter', 'arducopter', 'singlecopter'), @('coaxcopter', 'arducopter', 'coaxcopter'), @('heli', 'arducopter-heli', 'heli')
)
foreach ($f in $frames) {
    Write-Output "=== layout: $($f[2])"
    $p = Start-Frame $f[0] $f[1] 'ml-sitl'
    try { & "$bin\PageMotorLayoutProbe.exe" $isolated $out 5760 "layout-$($f[2]).txt" | Out-Null }
    finally {
        wsl.exe -d Ubuntu-E -e bash /home/think/frame-page-sitl.sh stop ml-sitl $evWsl "sitl-$($f[2]).log"
        if ($p -and -not $p.HasExited) { $p.Kill() }
    }
}
