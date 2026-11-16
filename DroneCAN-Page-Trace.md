# DroneCAN page trace

Scope: disconnected `ConfigDroneCAN` in the original Mission Planner release executable, driven by a C# reflection harness on 16 November 2026. The form was shown off-screen and rendered with `DrawToBitmap`; no person operated the application. This is partial execution evidence for a modified copy, not original-GUI coverage. No simulator or real vehicle was connected.

## Method and provenance

`research-tools/PageDroneCANProbe.cs` follows the existing page-probe pattern: resolve assemblies from the isolated directory, construct the page on an STA thread, show a 1100 by 760 host, pump WinForms events, call the original methods by reflection, record control state and save PNGs. `research-tools/run-dronecan-probe.ps1` compiles it with the .NET Framework compiler. Existing output directories are refused. A 45-second process watchdog retains a failure log rather than hanging indefinitely.

The executed sibling `mission-planner-isolated/MissionPlanner.exe` has SHA-256 `a49e30e2cd635836cd737f112f419da2d3c46c59716ee08122e2986013b79f2a`, matching the portable release. Its assembly version is `1.3.9384.38250`; the project identifies this release as Mission Planner 1.3.83. `MissionPlanner.Utilities.dll` differs from portable because the isolated environment redirects data paths. `MissionPlanner.Comms.dll` and `DroneCAN.dll` match portable. Full hashes are in `gui-dronecan-evidence-run3-initial-can/binary-provenance.json`.

The existing REA main-executable SQLite index identifies type `0x020001FE`. `rea-methods.json` retains its indexed methods and IL hashes. Runtime log tokens match `Activate` (`0x06000E15`), `but_connect_Click` (`0x06000E30`) and `Deactivate` (`0x06000E1F`). Reflection executes the original methods; source comparison below explains the captured state.

Without normal application startup, `MainV2.comPort.BaseStream` was null. The successful harness installs a closed `CommsInjection` object, an in-memory transport, without calling a connection method. The message-box hook logs and answers Cancel. Only SLCAN's disconnected warning path is exercised; the handler returns on Cancel before its serial-open path. Selecting multicast interfaces enumerates local network-interface choices but does not start multicast forwarding. Network packets were not independently monitored.

Example from the normal repository layout:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File research-tools/run-dronecan-probe.ps1 `
  -Isolated '..\mission-planner-isolated' `
  -Output '.\gui-dronecan-evidence-run4-repeat'
```

For a linked worktree in another parent directory, pass the isolated directory explicitly.

## Observed results

Successful capture: `gui-dronecan-evidence-run3-initial-can/`, exit 0, 13 PASS assertions, zero failed assertions, one SLCAN message box. `controls.csv` contains 35 controls including the page. `activated.png`, `cancelled-slcan.png` and `deactivated.png` record the corresponding rendered states.

| Action | Direct observation |
|---|---|
| `Activate()` | Starts an enabled timer with interval 1000 ms and populates five interface choices. |
| Select SLCAN, MAVLinkCAN1 or MAVLinkCAN2 | Network-interface selector is hidden. No Connect action was taken for the MAVLink choices. |
| Select MCastCan1 or MCastCan2 | Network-interface selector becomes visible. No multicast connection was started. |
| Select SLCAN, invoke Connect, answer Cancel | Warning reports no MAVLink connection. Afterwards `isConnected=True`, button text is `Disconnect`, and both selectors are disabled. The initial CAN object is unchanged and the in-memory MAVLink stream remains closed. |
| Invoke Connect handler again | Takes the disconnect branch: `isConnected=False`, button text becomes `Connect`, both selectors enabled. |
| `Deactivate()` | Timer stops, CAN field becomes null and connection flag remains false. |

The cancellation state was observed in both runs 2 and 3. It is a UI state mismatch in this harness: the page presents a Disconnect action after the connection warning was cancelled. It does not establish that a CAN link was created.

## Check against source

`mission-planner-1.3.83-source/GCSViews/ConfigurationView/ConfigDroneCAN.cs`:

- Lines 40–55: `Activate` starts the timer, binds connection enums and enumerates suitable local network interfaces.
- Lines 220–231: `startslcan` checks the closed MAVLink stream, shows OK/Cancel warning and returns when the answer is not OK.
- Line 463: CAN field has a `new DroneCAN.DroneCAN()` initializer. A non-null CAN field alone is not connection evidence.
- Lines 652–678: `Deactivate` calls `Disconnect`, then stops the timer; `Disconnect` clears CAN state and resets controls.
- Lines 1605–1651: Connect sets selectors disabled, text `Disconnect` and `isConnected=true` before dispatching to `startslcan`; no rollback follows its cancelled return.
- Lines 1653–1672: selector event toggles network-interface visibility by connection type.

## Retained failed attempts

1. `gui-dronecan-evidence-run1-null-stream/`: exit 1, `NullReferenceException` during harness transport inspection, before page construction. Original attempt source and log retained.
2. `gui-dronecan-evidence-run2-closed-injection/`: exit 1 after all actions ran. The assertion that Cancel leaves the CAN field null was wrong: the field is initialized at construction. Captures, log and that attempt's source are retained. This was a harness expectation failure, not an observed application exception.
3. Run 3 tests object identity against the initial CAN field and separately verifies the MAVLink stream remains closed. It retains the same observed cancellation mismatch.

## Not covered

CAN forwarding, actual serial connection, multicast traffic, node discovery, table actions, parameter editing, node restart, firmware update, packet loss, reconnect, normal MainV2 startup, a visible human-operated GUI and real hardware. Coverage stays partial at L3 with `gui_kind=modified-copy`; the `L3+gui` target remains open.
