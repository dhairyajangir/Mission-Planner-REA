# Press individual motor buttons of the original ConfigMotorTest page against disposable ArduCopter SITLs of the single and coax copter frames, with an independent
# SERVO_OUTPUT_RAW observer, to see what the extra buttons 7 and 8 (the page draws eight, the vehicle has six test sequences) and "Test all motors" do.
# Output: sitl-evidence/motor-buttons/. Simulator only, never a real vehicle.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$project = Split-Path -Parent $repo
$isolated = Join-Path $project 'mission-planner-isolated'
$out = Join-Path $repo 'sitl-evidence\motor-buttons'
$bin = Join-Path $env:TEMP 'motor-buttons-probe'
New-Item -ItemType Directory -Force $out, $bin | Out-Null
$csc = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
& $csc /nologo /target:exe /out:"$bin\PageMotorButtonsProbe.exe" /r:System.Windows.Forms.dll /r:System.Drawing.dll "$repo\research-tools\PageMotorButtonsProbe.cs"
if ($LASTEXITCODE -ne 0) { throw "compile failed" }
$rw = '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload'
wsl.exe -d Ubuntu-E -e cp "$rw/research-tools/frame-page-sitl.sh" /home/think/frame-page-sitl.sh
wsl.exe -d Ubuntu-E -e cp "$rw/research-tools/sitl-servo-observer.py" /home/think/sitl-servo-observer.py
wsl.exe -d Ubuntu-E -e cp "$rw/research-tools/servo-observer-run.sh" /home/think/servo-observer-run.sh

$frames = @(@('singlecopter', 'singlecopter'), @('coaxcopter', 'coaxcopter'))
foreach ($f in $frames) {
    Write-Output "=== buttons: $($f[1])"
    $p = Start-Process -FilePath wsl.exe -ArgumentList @('-d', 'Ubuntu-E', '-e', 'bash', '/home/think/frame-page-sitl.sh', 'run', $f[0], 'arducopter', 'mb-sitl') -WindowStyle Hidden -PassThru
    wsl.exe -d Ubuntu-E -e bash /home/think/frame-page-sitl.sh wait mb-sitl
    Start-Sleep -Seconds 10
    $c = New-Object System.Net.Sockets.TcpClient('127.0.0.1', 5760)
    $s = $c.GetStream(); $s.ReadTimeout = 15000
    $buf = New-Object byte[] 512
    $n = $s.Read($buf, 0, 512)
    Write-Output "prime: simulator sent $n bytes"
    $c.Close()
    Start-Sleep -Seconds 3
    $obs = Start-Process -FilePath wsl.exe -ArgumentList @('-d', 'Ubuntu-E', '-e', 'bash', '/home/think/servo-observer-run.sh') -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 2
    try {
        & "$bin\PageMotorButtonsProbe.exe" $isolated $out 5760 "$($f[1])-log.txt" 'motor:5' 'motor:6' 'motor:7' 'motor:8' 'all' 'stop' | Tee-Object -FilePath "$out\$($f[1])-console.txt"
        $obs.WaitForExit(120000) | Out-Null
    } finally {
        wsl.exe -d Ubuntu-E -e bash /home/think/frame-page-sitl.sh stop mb-sitl "$rw/sitl-evidence/motor-buttons" "sitl-$($f[1]).log"
        wsl.exe -d Ubuntu-E -e cp /home/think/servo-observer.csv "$rw/sitl-evidence/motor-buttons/$($f[1])-servo-observer.csv"
        wsl.exe -d Ubuntu-E -e cp /home/think/servo-observer.csv.statustext.txt "$rw/sitl-evidence/motor-buttons/$($f[1])-statustext.txt"
        if ($p -and -not $p.HasExited) { $p.Kill() }
    }
    python -I "$repo\research-tools\analyze-motor-buttons.py" $out $f[1] "$out\$($f[1])-summary.csv"
}
