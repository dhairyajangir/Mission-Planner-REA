param(
    [string]$Isolated = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'mission-planner-isolated'),
    [string]$Output = (Join-Path (Split-Path -Parent $PSScriptRoot) 'gui-dronecan-evidence')
)
$ErrorActionPreference = 'Stop'
# Never overwrite evidence, including failed attempts.
if (Test-Path -LiteralPath $Output) { throw "Evidence exists: $Output. Pass a sibling -run2-<reason> output path." }
$build = Join-Path $env:TEMP ('dronecan-probe-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $build | Out-Null
$csc = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
& $csc /nologo /target:exe /out:"$build\PageDroneCANProbe.exe" /r:System.Windows.Forms.dll /r:System.Drawing.dll (Join-Path $PSScriptRoot 'PageDroneCANProbe.cs')
if ($LASTEXITCODE -ne 0) { throw 'Probe compilation failed' }
& "$build\PageDroneCANProbe.exe" $Isolated $Output
$probeExit = $LASTEXITCODE
if (Test-Path -LiteralPath $Output) {
    Set-Content -LiteralPath (Join-Path $Output 'exit-code.txt') -Value $probeExit -Encoding ASCII
}
if ($probeExit -ne 0) { throw "Probe failed: $probeExit. Retain this output; use a new sibling directory for retry." }
