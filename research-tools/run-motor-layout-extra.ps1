# The frame types that are in the firmware but not in the page's APMotorLayout.json (quad Y4 = type 19, octa-quad X_COR = 20 and CW_X_COR = 21) are not in the simulator's
# frame list, so each is set by parameter: sitl-frame-motor-sweep.py <model>:FRAME_TYPE=n leaves a work directory with the stored parameters, the simulator is started
# again from it without wiping, and PageMotorLayoutProbe lists what the original ConfigMotorTest page draws. Output: sitl-evidence/motor-layout-page/extra-*.txt.
# Simulator only, never a real vehicle.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$project = Split-Path -Parent $repo
$isolated = Join-Path $project 'mission-planner-isolated'
$out = Join-Path $repo 'sitl-evidence\motor-layout-page'
$bin = Join-Path $env:TEMP 'motor-layout-probe'
$rw = '/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload'
wsl.exe -d Ubuntu-E -e cp "$rw/research-tools/frame-page-sitl.sh" /home/think/frame-page-sitl.sh
wsl.exe -d Ubuntu-E -e cp "$rw/research-tools/sitl-frame-motor-sweep.py" /home/think/sitl-frame-motor-sweep.py
wsl.exe -d Ubuntu-E -e cp "$rw/research-tools/prepare-frame-type.sh" /home/think/prepare-frame-type.sh

foreach ($f in @(@('+', 'quad', 19, 'y4'), @('octa-quad', 'octa-quad', 20, 'octaquad-xcor'), @('octa-quad', 'octa-quad', 21, 'octaquad-cwxcor'))) {
    Write-Output "=== extra: $($f[3]) (model $($f[1]), FRAME_TYPE $($f[2]))"
    wsl.exe -d Ubuntu-E -e bash /home/think/prepare-frame-type.sh $f[1] $f[2] "fp-extra"
    $p = Start-Process -FilePath wsl.exe -ArgumentList @('-d', 'Ubuntu-E', '-e', 'bash', '/home/think/frame-page-sitl.sh', 'run', $f[0], 'arducopter', 'fp-extra', 'nowipe') -WindowStyle Hidden -PassThru
    wsl.exe -d Ubuntu-E -e bash /home/think/frame-page-sitl.sh wait fp-extra
    Start-Sleep -Seconds 10
    $c = New-Object System.Net.Sockets.TcpClient('127.0.0.1', 5760)
    $s = $c.GetStream(); $s.ReadTimeout = 15000
    $buf = New-Object byte[] 512
    $n = $s.Read($buf, 0, 512)
    Write-Output "prime: simulator sent $n bytes"
    $c.Close()
    Start-Sleep -Seconds 3
    try { & "$bin\PageMotorLayoutProbe.exe" $isolated $out 5760 "extra-$($f[3]).txt" | Out-Null }
    finally {
        wsl.exe -d Ubuntu-E -e bash /home/think/frame-page-sitl.sh stop fp-extra "$rw/sitl-evidence/motor-layout-page" "sitl-extra-$($f[3]).log"
        if ($p -and -not $p.HasExited) { $p.Kill() }
    }
}
