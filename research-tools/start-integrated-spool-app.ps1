param([string]$RunName = 'integrated-spool-probe')
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$portable = Join-Path $project 'mission-planner-isolated'
$runtime = Join-Path $project 'mission-planner-runtime'
$probe = Join-Path $project 'sitl-evidence\integrated-app-spool-probe.py'
$run = Join-Path (Join-Path $project 'sitl-evidence') $RunName
if (-not (Test-Path -LiteralPath $run -PathType Container)) { throw 'Relay run directory not found.' }
$env:MP_INTEGRATED_RESULT = Join-Path $run 'application-result.txt'
$env:MP_SPOOL_DIR = Join-Path $run 'spool'
$env:USERPROFILE = $runtime
$env:APPDATA = Join-Path $runtime 'AppData\Roaming'
$env:LOCALAPPDATA = Join-Path $runtime 'AppData\Local'
$env:PROGRAMDATA = Join-Path $runtime 'ProgramData'
$arguments = '-script "' + $probe + '"'
$proc = Start-Process -FilePath (Join-Path $portable 'MissionPlanner.exe') -ArgumentList $arguments -WorkingDirectory $portable -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $run 'application-stdout.log') -RedirectStandardError (Join-Path $run 'application-stderr.log')
Write-Output "Mission Planner test PID: $($proc.Id)"
if (-not $proc.WaitForExit(120000)) {
    Stop-Process -Id $proc.Id -Force
    $proc.WaitForExit()
    Write-Output 'Stopped bounded application probe after 120 seconds.'
}
