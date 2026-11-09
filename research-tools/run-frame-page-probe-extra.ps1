# State of the original ConfigFrameClassType page against frames whose FRAME_TYPE has no button on it (Betaflight X = 12, DJI X = 13, clockwise X = 14, and the
# hexa/octa variants of them). Reuses PageFrameProbe.exe built by run-frame-page-probe.ps1. Output: sitl-evidence/frame-page/state-<label>.txt. Simulator only.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$project = Split-Path -Parent $repo
$isolated = Join-Path $project 'mission-planner-isolated'
$out = Join-Path $repo 'sitl-evidence\frame-page'
$bin = Join-Path $env:TEMP 'frame-page-probe'
$csc = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
& $csc /nologo /target:exe /out:"$bin\PageFrameProbe.exe" /r:System.Windows.Forms.dll /r:System.Drawing.dll "$repo\research-tools\PageFrameProbe.cs"
if ($LASTEXITCODE -ne 0) { throw "compile failed" }
$rw = '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload'
wsl.exe -d Ubuntu-E -e cp "$rw/research-tools/frame-page-sitl.sh" /home/think/frame-page-sitl.sh
foreach ($f in @(@('bfx', 'quad-bfx'), @('djix', 'quad-djix'), @('cwx', 'quad-cwx'), @('hexa-dji', 'hexa-dji'), @('octa-cwx', 'octa-cwx'))) {
    Write-Output "=== state: $($f[1])"
    $p = Start-Process -FilePath wsl.exe -ArgumentList @('-d', 'Ubuntu-E', '-e', 'bash', '/home/think/frame-page-sitl.sh', 'run', $f[0], 'arducopter', 'fp-sitl') -WindowStyle Hidden -PassThru
    wsl.exe -d Ubuntu-E -e bash /home/think/frame-page-sitl.sh wait fp-sitl
    Start-Sleep -Seconds 10
    $c = New-Object System.Net.Sockets.TcpClient('127.0.0.1', 5760)
    $s = $c.GetStream(); $s.ReadTimeout = 15000
    $buf = New-Object byte[] 512
    $n = $s.Read($buf, 0, 512)
    Write-Output "prime: simulator sent $n bytes"
    $c.Close()
    Start-Sleep -Seconds 3
    try { & "$bin\PageFrameProbe.exe" $isolated $out 5760 "state-$($f[1]).txt" | Out-Null }
    finally {
        wsl.exe -d Ubuntu-E -e bash /home/think/frame-page-sitl.sh stop fp-sitl "$rw/sitl-evidence/frame-page" "sitl-state-$($f[1]).log"
        if ($p -and -not $p.HasExited) { $p.Kill() }
    }
}
