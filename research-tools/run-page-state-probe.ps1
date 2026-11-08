# Build PageStateProbe.cs and run it for every page that rendered in mission-planner-gui-faces/connected/faces-index.csv against a
# disposable ArduCopter SITL (Ubuntu-E), using the launch shape that worked for PageActionProbe (see Setup-Page-Actions-Trace.md).
# Output: sitl-evidence/page-state/. Simulator only.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$project = Split-Path -Parent $repo
$isolated = Join-Path $project 'mission-planner-isolated'
$out = Join-Path $repo 'sitl-evidence\page-state'
$bin = Join-Path $env:TEMP 'page-state-probe'
New-Item -ItemType Directory -Force $out, $bin | Out-Null
$pageList = Join-Path $bin 'pages.txt'
(Import-Csv (Join-Path $repo 'mission-planner-gui-faces\connected\faces-index.csv') | Where-Object { $_.status -eq 'ok' } | ForEach-Object { $_.page }) | Set-Content -Path $pageList -Encoding ascii
$csc = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
& $csc /nologo /target:exe /out:"$bin\PageStateProbe.exe" /r:System.Windows.Forms.dll /r:System.Drawing.dll "$repo\research-tools\PageStateProbe.cs"
if ($LASTEXITCODE -ne 0) { throw "compile failed" }
$sh = '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload/research-tools/page-action-sitl.sh'
wsl.exe -d Ubuntu-E -e cp $sh /home/think/page-action-sitl-run.sh
wsl.exe -d Ubuntu-E -e rm -rf /home/think/page-action-sitl
$wslProc = Start-Process -FilePath wsl.exe -ArgumentList @('-d', 'Ubuntu-E', '-e', 'bash', '/home/think/page-action-sitl-run.sh', 'run') -WindowStyle Hidden -PassThru
wsl.exe -d Ubuntu-E -e bash $sh wait
Start-Sleep -Seconds 10
$c = New-Object System.Net.Sockets.TcpClient('127.0.0.1', 5760)
$s = $c.GetStream(); $s.ReadTimeout = 15000
$buf = New-Object byte[] 512
$n = $s.Read($buf, 0, 512)
Write-Output "prime: simulator sent $n bytes"
$c.Close()
Start-Sleep -Seconds 3
try {
    & "$bin\PageStateProbe.exe" $isolated $out 5760 $pageList | Tee-Object -FilePath "$out\console.txt"
} finally {
    wsl.exe -d Ubuntu-E -e bash $sh stop '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload/sitl-evidence/page-state'
    if ($wslProc -and -not $wslProc.HasExited) { $wslProc.Kill() }
}
