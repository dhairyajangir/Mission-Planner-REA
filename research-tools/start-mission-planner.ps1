$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$portable = Join-Path $project 'mission-planner-isolated'
$isolated = Join-Path $project 'mission-planner-runtime'
New-Item -ItemType Directory -Force -Path $isolated | Out-Null
$env:USERPROFILE = $isolated
$env:APPDATA = Join-Path $isolated 'AppData\Roaming'
$env:LOCALAPPDATA = Join-Path $isolated 'AppData\Local'
$env:PROGRAMDATA = Join-Path $isolated 'ProgramData'
New-Item -ItemType Directory -Force -Path $env:APPDATA, $env:LOCALAPPDATA, $env:PROGRAMDATA | Out-Null
$proc = Start-Process -FilePath (Join-Path $portable 'MissionPlanner.exe') -WorkingDirectory $portable -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $isolated 'stdout.log') -RedirectStandardError (Join-Path $isolated 'stderr.log')
Write-Output "MissionPlanner PID: $($proc.Id)"
if (-not $proc.WaitForExit(20000)) {
    Stop-Process -Id $proc.Id -Force
    $proc.WaitForExit()
    Write-Output 'Stopped bounded startup probe after 20 seconds.'
}
Write-Output "MissionPlanner exit code: $($proc.ExitCode)"
