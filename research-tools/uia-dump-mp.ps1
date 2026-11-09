# Launch the research copy of Mission Planner 1.3.83 (data-redirected isolated copy) beside a disposable Copter simulator and dump the Windows UI Automation tree of
# its main window (name, control type, automation id, patterns offered) to sitl-evidence/live-gui-uia/uia-tree.txt. Only that one window is read; nothing is clicked or typed.
# Simulator only, never a real vehicle.
param([int]$WaitSeconds = 30, [int]$MaxDepth = 4)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$repo = Split-Path -Parent $PSScriptRoot
$project = Split-Path -Parent $repo
$iso = Join-Path $project 'mission-planner-isolated'
$out = Join-Path $repo 'sitl-evidence\live-gui-uia'
New-Item -ItemType Directory -Force $out | Out-Null
wsl.exe -d Ubuntu-E -e cp "/mnt/e/DroneProject/The Drone Project/mission-planner-rea-upload/research-tools/frame-page-sitl.sh" /home/think/frame-page-sitl.sh
$sitl = Start-Process -FilePath wsl.exe -ArgumentList @('-d', 'Ubuntu-E', '-e', 'bash', '/home/think/frame-page-sitl.sh', 'run', '+', 'arducopter', 'uia-sitl') -WindowStyle Hidden -PassThru
wsl.exe -d Ubuntu-E -e bash /home/think/frame-page-sitl.sh wait uia-sitl
$mp = Start-Process -FilePath "$iso\MissionPlanner.exe" -WorkingDirectory $iso -PassThru
Start-Sleep -Seconds $WaitSeconds
$root = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $mp.Id)
$wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)
"windows of process $($mp.Id): $($wins.Count)" | Tee-Object -FilePath "$out\uia-tree.txt"
function Dump($el, $depth) {
    if ($depth -gt $MaxDepth) { return }
    $kids = $el.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($k in $kids) {
        $c = $k.Current
        $pat = ($k.GetSupportedPatterns() | ForEach-Object { $_.ProgrammaticName -replace 'PatternIdentifiers.Pattern', '' }) -join ','
        ('{0}{1} | {2} | id={3} | class={4} | enabled={5} | offscreen={6} | {7}' -f ('  ' * $depth), $c.ControlType.ProgrammaticName.Replace('ControlType.', ''), $c.Name, $c.AutomationId, $c.ClassName, $c.IsEnabled, $c.IsOffscreen, $pat) | Add-Content -Path "$out\uia-tree.txt"
        Dump $k ($depth + 1)
    }
}
foreach ($w in $wins) { ('WINDOW {0} | {1}' -f $w.Current.Name, $w.Current.ClassName) | Add-Content -Path "$out\uia-tree.txt"; Dump $w 1 }
Get-Content "$out\uia-tree.txt" | Measure-Object -Line | ForEach-Object { "lines: $($_.Lines)" }
