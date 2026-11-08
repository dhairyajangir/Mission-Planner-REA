# Build PageActionProbe.cs with the .NET Framework compiler and run it against a disposable ArduCopter SITL started in WSL (Ubuntu-E).
# Output: sitl-evidence/page-actions/. Simulator only. Usage: powershell -File run-page-action-probe.ps1
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$project = Split-Path -Parent $repo                       # "The Drone Project"
$isolated = Join-Path $project 'mission-planner-isolated'
$out = Join-Path $repo 'sitl-evidence\page-actions'
$bin = Join-Path $env:TEMP 'page-action-probe'
New-Item -ItemType Directory -Force $out, $bin | Out-Null
$csc = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
& $csc /nologo /target:exe /out:"$bin\PageActionProbe.exe" /r:System.Windows.Forms.dll /r:System.Drawing.dll "$repo\research-tools\PageActionProbe.cs"
if ($LASTEXITCODE -ne 0) { throw "compile failed" }
$sh = '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload/research-tools/page-action-sitl.sh'
# Start-Process splits arguments at spaces and the repository path contains one, so run a copy of the helper from a path without spaces
wsl.exe -d Ubuntu-E -e cp $sh /home/think/page-action-sitl-run.sh
# the readiness check reads the simulator log, so a log left by an earlier run must not exist (it made the first wait return at once)
wsl.exe -d Ubuntu-E -e rm -rf /home/think/page-action-sitl
$wslProc = Start-Process -FilePath wsl.exe -ArgumentList @('-d', 'Ubuntu-E', '-e', 'bash', '/home/think/page-action-sitl-run.sh', 'run') -WindowStyle Hidden -PassThru
# wait until the simulator reports it is waiting for a client (startup time varies). The wait lives in the helper script because
# PowerShell 5.1 strips double quotes from inline bash -c strings passed to wsl.exe.
wsl.exe -d Ubuntu-E -e bash $sh wait
# Prime the simulator: it only initialises after its first client connects, and Mission Planner's Open() gave up during that start-up
# (the first connection failed with "Not Connected" in every run; the only run that worked came after a plain client had connected).
# WSL's localhost forwarding can lag behind the listener: an early connection is accepted on the Windows side and closed at once
# (0 bytes). Retry until the simulator really answers.
#
# Observed: a connection made within a few seconds of "Waiting for connection" is closed at once and the simulator then exits (port
# refused afterwards), so a retry loop cannot help; the one run that worked connected about 8 s after the simulator started listening.
Start-Sleep -Seconds 10
$primed = $false
for ($k = 1; $k -le 1 -and -not $primed; $k++) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient('127.0.0.1', 5760)
        $s = $c.GetStream(); $s.ReadTimeout = 15000
        $buf = New-Object byte[] 512
        $n = $s.Read($buf, 0, 512)
        Write-Output "prime attempt ${k}: simulator sent $n bytes"
        if ($n -gt 0) { $primed = $true }
        $c.Close()
    } catch { Write-Output ("prime attempt ${k} failed: " + $_.Exception.Message) }
    if (-not $primed) { Start-Sleep -Seconds 3 }
}
Start-Sleep -Seconds 3
try {
    & "$bin\PageActionProbe.exe" $isolated $out 5760 | Tee-Object -FilePath "$out\console.txt"
} finally {
    wsl.exe -d Ubuntu-E -e bash $sh stop
    if ($wslProc -and -not $wslProc.HasExited) { $wslProc.Kill() }
}
