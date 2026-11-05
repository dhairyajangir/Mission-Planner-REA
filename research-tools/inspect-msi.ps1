param([Parameter(Mandatory=$true)][string]$Path)
$ErrorActionPreference = 'Stop'
$installer = New-Object -ComObject WindowsInstaller.Installer
$db = $installer.GetType().InvokeMember('OpenDatabase','InvokeMethod',$null,$installer,@((Resolve-Path -LiteralPath $Path).Path,0))
function Query-Msi([string]$Sql, [int]$Fields) {
    $view = $db.GetType().InvokeMember('OpenView','InvokeMethod',$null,$db,@($Sql))
    $view.GetType().InvokeMember('Execute','InvokeMethod',$null,$view,$null) | Out-Null
    while ($null -ne ($record = $view.GetType().InvokeMember('Fetch','InvokeMethod',$null,$view,$null))) {
        $values = for ($i=1; $i -le $Fields; $i++) { $record.GetType().InvokeMember('StringData','GetProperty',$null,$record,@($i)) }
        ,$values
    }
    $view.GetType().InvokeMember('Close','InvokeMethod',$null,$view,$null) | Out-Null
}
Write-Output 'PROPERTIES'
Query-Msi 'SELECT `Property`, `Value` FROM `Property`' 2 | Where-Object { $_[0] -in @('ProductName','ProductVersion','ProductCode','Manufacturer') } | ForEach-Object { $_ -join "`t" }
Write-Output 'MAIN APPLICATION CANDIDATES'
Query-Msi 'SELECT `File`, `FileName`, `Component_`, `FileSize`, `Version` FROM `File`' 5 | Where-Object { $_[1] -match '(?i)missionplanner.*\.exe|mission planner.*\.exe' } | ForEach-Object { $_ -join "`t" }
Write-Output 'MEDIA'
Query-Msi 'SELECT `DiskId`, `LastSequence`, `Cabinet` FROM `Media`' 3 | ForEach-Object { $_ -join "`t" }
