# Read-only capability inventory. Output omits guest names, hostnames, accounts and device IDs.
$ErrorActionPreference = 'Stop'
$os = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
$result = [ordered]@{
    checked_utc = (Get-Date).ToUniversalTime().ToString('o')
    edition = $os.EditionID
    build = $os.CurrentBuild
    admin_token = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
function ErrorKind($exception) {
    if ($exception.Message -match 'elevation|elevated|permission|access.*denied|privilege|authorization') { return 'permission required' }
    return $exception.GetType().Name
}
try {
    $feature = @(Get-CimInstance -ClassName Win32_OptionalFeature -Filter "Name = 'Containers-DisposableClientVM'")
    $result.sandbox_cim = if ($feature.Count -eq 0) { 'no feature row' } else { @($feature | ForEach-Object { [int]$_.InstallState }) }
} catch { $result.sandbox_cim = ErrorKind $_.Exception }
try {
    $result.sandbox_dism = (Get-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM).State.ToString()
} catch { $result.sandbox_dism = ErrorKind $_.Exception }
try {
    $result.sandbox_appx_count = @(Get-AppxPackage -Name '*WindowsSandbox*').Count
} catch { $result.sandbox_appx_count = ErrorKind $_.Exception }
$result.wsb_file_association = Test-Path -LiteralPath 'Registry::HKEY_CLASSES_ROOT\.wsb'
$commands = [ordered]@{}
foreach ($name in @('WindowsSandbox.exe','WindowsSandboxClient.exe','wsb.exe','Get-VM','VBoxManage.exe','vmrun.exe','qemu-system-x86_64.exe')) {
    $commands[$name] = [bool](Get-Command $name -ErrorAction SilentlyContinue)
}
$result.commands = $commands
$result.known_launchers = [ordered]@{
    sandbox_system32 = Test-Path -LiteralPath "$env:SystemRoot\System32\WindowsSandbox.exe"
    sandbox_client_system32 = Test-Path -LiteralPath "$env:SystemRoot\System32\WindowsSandboxClient.exe"
    virtualbox = Test-Path -LiteralPath "$env:ProgramFiles\Oracle\VirtualBox\VirtualBox.exe"
    vmware_workstation = (Test-Path -LiteralPath "${env:ProgramFiles(x86)}\VMware\VMware Workstation\vmware.exe") -or (Test-Path -LiteralPath "$env:ProgramFiles\VMware\VMware Workstation\vmware.exe")
    qemu = Test-Path -LiteralPath "$env:ProgramFiles\qemu\qemu-system-x86_64.exe"
}
$services = [ordered]@{}
foreach ($name in @('vmms','vmcompute')) {
    $service = Get-Service $name -ErrorAction SilentlyContinue
    $services[$name] = if ($service) { $service.Status.ToString() } else { 'not found' }
}
$result.services = $services
try { $result.hyperv_guest_count = @(Get-VM).Count } catch { $result.hyperv_guest_count = ErrorKind $_.Exception }
$vboxConfig = "$env:USERPROFILE\.VirtualBox\VirtualBox.xml"
$vmwareConfig = "$env:APPDATA\VMware\inventory.vmls"
$result.virtualbox_current_user_registry = Test-Path -LiteralPath $vboxConfig
$result.vmware_current_user_inventory = Test-Path -LiteralPath $vmwareConfig
$result | ConvertTo-Json -Depth 4
