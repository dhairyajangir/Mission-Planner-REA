# Native Windows GUI feasibility

On 22 November 2026 at 01:04 IST, the real desktop account on Windows Professional build 26300 reported `InstallState=2` for `Containers-DisposableClientVM`. Microsoft defines 2 as **Disabled**. A `.wsb` file association existed, but the account had zero Windows Sandbox app packages and no discoverable Sandbox executable. The session started no native Mission Planner process. [Captured host state](host-state.json) · [Microsoft optional-feature state definitions](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-optionalfeature)

Hyper-V Virtual Machine Management and Host Compute services were running. The account could load `Get-VM`, but Windows denied permission to enumerate guests. An administrator-owned Windows guest might exist; this check could establish neither its availability nor authorization to use it. The probes found no VirtualBox, VMware Workstation or QEMU launcher in the command path or the conventional installation locations checked, and no current-user VirtualBox or VMware inventory. A separate process count found zero running native Mission Planner processes.

The project workspace contained a Linux WSL `ext4.vhdx` and two VHDL source files whose `.vhd` extension matched the image scan. No Windows Sandbox configuration, Windows guest image or virtual-machine configuration matched that scan. A fresh disconnected native-Windows observation therefore remains unverified. Sandbox would require a feature change; a pre-existing guest would require a separate access check. The host profile and Windows features were left untouched.

## Existing capture provenance

At this check, the coverage matrix contained 22 rows with `original` in `gui_kind`. Each row's note identified Linux/Mono. Earlier native Windows live-window tests used the isolated copy with two redirected user-data methods. Those runs establish behavior on that copy. Launching the ZIP directly on the host would use the current Windows Documents and shared application-data paths. [Coverage matrix](../coverage/matrix.csv) · [Native Windows observations](../Mission-Planner-UI-Observations.md) · [Pinned settings implementation](../mission-planner-1.3.83-source/ExtLibs/Utilities/Settings.cs)

## Reproduce

Run the read-only inventory with the actual desktop account, outside the agent's restricted user namespace. It prints feature state, launcher presence and access results without exposing host, account, device or guest identifiers.

```powershell
powershell.exe -NoProfile -File .\native-windows-gui-feasibility\inspect-host.ps1
@(Get-Process -Name MissionPlanner -ErrorAction SilentlyContinue).Count
rg --files --hidden --no-ignore -g '!**/.git/**' -g '*.wsb' -g '*.vbox' -g '*.vmx' -g '*.vhd' -g '*.vhdx' -g '*.vmdk' -g '*.qcow2' -g '*.iso' E:\DroneProject
```

The DISM feature query separately required an administrator token. The CIM result provided the feature state in the ordinary account. The filesystem search covered the project workspace only. [Inventory script](inspect-host.ps1) · [Microsoft Windows Sandbox prerequisites](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-install)
