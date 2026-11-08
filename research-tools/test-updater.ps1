# Exercise Mission Planner's bundled Updater.exe in a scratch directory with fake files. No network, no real install.
# Usage: powershell -File test-updater.ps1 <Updater.exe> <scratch dir> <output dir>
param([string]$Exe, [string]$Work, [string]$Out)
$ErrorActionPreference = 'Stop'
# The shipped manifest requires administrator rights (Updater/app.manifest). For this scratch-directory test only, ask Windows to
# run the child as the invoking user instead of prompting for elevation; nothing outside the scratch directory is touched.
$env:__COMPAT_LAYER = 'RunAsInvoker'
function Setup($dir, [bool]$dotnew) {
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    New-Item -ItemType Directory -Force "$dir\sub" | Out-Null
    Copy-Item $Exe "$dir\Updater.exe"
    Set-Content "$dir\a.dll" 'old-a'; Set-Content "$dir\a.dll.new" 'new-a'
    Set-Content "$dir\b.dll.new" 'new-b'                       # no existing b.dll
    Set-Content "$dir\stale.dll.old" 'stale'                   # should be deleted
    Set-Content "$dir\sub\d.dll" 'old-d'; Set-Content "$dir\sub\d.dll.new" 'new-d'
    Set-Content "$dir\Updater.exe.new" 'self-update'           # cannot self-update: left alone
    if ($dotnew) { Set-Content "$dir\.new" 'dot-new' }         # a file literally named .new
}
function Listing($dir) { Get-ChildItem $dir -Recurse -File -Force | Where-Object { $_.Name -ne 'Updater.exe' } | ForEach-Object { '{0} = {1}' -f $_.FullName.Substring($dir.Length + 1), (Get-Content $_.FullName -ErrorAction SilentlyContinue | Select-Object -First 1) } | Sort-Object }
function RunCase($name, [bool]$dotnew, [bool]$lockA) {
    $d = Join-Path $Work $name; Setup $d $dotnew
    $lock = $null
    if ($lockA) { $lock = [IO.File]::Open("$d\a.dll", 'Open', 'Read', 'None') }
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $p = Start-Process -FilePath "$d\Updater.exe" -WorkingDirectory $d -RedirectStandardOutput "$Out\$name-console.txt" -RedirectStandardError "$Out\$name-stderr.txt" -PassThru -WindowStyle Hidden
    $null = $p.WaitForExit(90000)
    if (-not $p.HasExited) { $p.Kill() }
    if ($lock) { $lock.Close() }
    "$name exited=$($p.HasExited) seconds=$([math]::Round($sw.Elapsed.TotalSeconds,1))" | Set-Content "$Out\$name-result.txt"
    Listing $d | Add-Content "$Out\$name-result.txt"
}
New-Item -ItemType Directory -Force $Out | Out-Null
RunCase 'case1-clean' $false $false
RunCase 'case2-locked-file' $false $true
RunCase 'case3-file-named-dot-new' $true $false
