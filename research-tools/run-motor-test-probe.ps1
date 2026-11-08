# Build PageMotorTestProbe.cs, start a disposable ArduCopter SITL (Ubuntu-E) with the launch shape that worked for PageActionProbe, run the
# original ConfigMotorTest page against it and, in parallel, record SERVO_OUTPUT_RAW from SERIAL1 with an independent pymavlink observer.
# Output: sitl-evidence/motor-test-page/. Simulator only, never a real vehicle.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$project = Split-Path -Parent $repo
$isolated = Join-Path $project 'mission-planner-isolated'
$out = Join-Path $repo 'sitl-evidence\motor-test-page'
$bin = Join-Path $env:TEMP 'motor-test-probe'
New-Item -ItemType Directory -Force $out, $bin | Out-Null
$csc = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
& $csc /nologo /target:exe /out:"$bin\PageMotorTestProbe.exe" /r:System.Windows.Forms.dll /r:System.Drawing.dll "$repo\research-tools\PageMotorTestProbe.cs"
if ($LASTEXITCODE -ne 0) { throw "compile failed" }
$sh = '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload/research-tools/page-action-sitl.sh'
wsl.exe -d Ubuntu-E -e cp $sh /home/think/page-action-sitl-run.sh
wsl.exe -d Ubuntu-E -e rm -rf /home/think/page-action-sitl
# observer wrapper without spaces in its path (Start-Process splits arguments at spaces)
$obsPy = '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload/research-tools/sitl-servo-observer.py'
wsl.exe -d Ubuntu-E -e cp $obsPy /home/think/sitl-servo-observer.py
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
# the observer runs for 90 s; it waits for SERIAL1, which the simulator opens once a client has connected to SERIAL0
wsl.exe -d Ubuntu-E -e cp '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload/research-tools/servo-observer-run.sh' /home/think/servo-observer-run.sh
$obs = Start-Process -FilePath wsl.exe -ArgumentList @('-d', 'Ubuntu-E', '-e', 'bash', '/home/think/servo-observer-run.sh') -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 2
try {
    & "$bin\PageMotorTestProbe.exe" $isolated $out 5760 | Tee-Object -FilePath "$out\console.txt"
    $obs.WaitForExit(120000) | Out-Null
} finally {
    wsl.exe -d Ubuntu-E -e bash $sh stop '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload/sitl-evidence/motor-test-page'
    wsl.exe -d Ubuntu-E -e cp /home/think/servo-observer.csv '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload/sitl-evidence/motor-test-page/servo-observer.csv'
    wsl.exe -d Ubuntu-E -e cp /home/think/servo-observer.csv.statustext.txt '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload/sitl-evidence/motor-test-page/servo-observer.statustext.txt'
    wsl.exe -d Ubuntu-E -e cp /home/think/servo-observer.out '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload/sitl-evidence/motor-test-page/servo-observer.out'
    if ($wslProc -and -not $wslProc.HasExited) { $wslProc.Kill() }
}
