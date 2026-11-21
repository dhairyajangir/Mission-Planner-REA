# Why opening Battery Monitor wrote BATT_VOLT_MULT

In the retained Mission Planner 1.3.83 session, opening Battery Monitor initiated the divider validation path. The application sent the simulator the same four bytes it had already received for the voltage multiplier. A separate parameter-storage operation followed.

## Release control flow

The release executable clears its startup flag at the end of `ConfigBatteryMonitoring.Activate`, explicitly calls the monitor-type and sensor-type selection handlers, then starts the page timer. The sensor-type handler calls the amps validation routine followed by `TXT_divider_Validated`. The latter gates on startup and control availability, parses the divider text as a single-precision float, promotes it to double and tries the parameter aliases `VOLT_DIVIDER`, then `BATT_VOLT_MULT`. These calls execute during activation without an edit or focus transition. The designer also connects the divider textbox's real `Validated` event to this routine. The page timer refreshes displayed voltage and current.

The application log records the characteristic sequence at lines 4342–4380. It opens Battery Monitor, skips the unchanged monitor and amps settings, tries the missing legacy divider alias and sends the multiplier. The observation log records a navigation click, followed by 37 seconds before the next navigation action. This historical capture does not record call stacks or individual focus events. The release's direct calls and matching log sequence establish the activation mechanism independently of the name of the event handler. [Application log](../gui-original-copter-sensors/sensors-FjBlM50a/release.log) · [Navigation log](../gui-original-copter-sensors/sensors-FjBlM50a/observation.log) · [Compiled instructions](release-il.txt) · [Page source](../mission-planner-1.3.83-source/GCSViews/ConfigurationView/ConfigBatteryMonitoring.cs) · [Designer](../mission-planner-1.3.83-source/GCSViews/ConfigurationView/ConfigBatteryMonitoring.Designer.cs)

## Why the unchanged value passes the change check

The release parameter object rounds its REAL32 public value before returning it as a double. Under the probe's invariant culture the object displays `10.1`. Parsing that text as a float and promoting the result to double produces a different double, so the release's exact equality check permits the write. The probe exercises the original MAVLink.dll's constructor, Value getter and ToString method. The wire representation comes from the original telemetry capture.

| Value | Release public double | Promoted parsed float | Exact comparison | Original → outgoing little-endian bytes |
| --- | --- | --- | --- | --- |
| Captured multiplier | 10.100000000000001 | 10.100000381469727 | Unequal | 9a 99 21 41 → 9a 99 21 41 |
| Offline control | 17 | 17 | Equal | 00 00 88 41 → 00 00 88 41 (candidate bytes) |

[Parameter representation](../mission-planner-1.3.83-source/ExtLibs/Mavlink/MAVLinkParam.cs) · [Parameter guard and storage logic](../mission-planner-1.3.83-source/ExtLibs/ArduPilot/Mavlink/MAVLinkInterface.cs) · [Probe output](release-il.txt)

## Wire timing

| UTC on 21 November 2026 | Recorded event |
| --- | --- |
| 19:08:22.224123 | Copter reports BATT_VOLT_MULT |
| 19:13:01 (seconds resolution) | Operator selects Battery Monitor |
| 19:13:04.237737 | Ground station sends BATT_VOLT_MULT to system 1, component 1 |
| 19:13:04.249853 | Copter echoes the same four bytes |
| 19:13:14.422378 | Ground station sends PREFLIGHT_STORAGE, command 245, first argument 1 |
| 19:13:38 (seconds resolution) | Next operator action, a navigation scroll |
| 19:14:08 (seconds resolution) | Operator selects Battery Monitor 2 |

The link's read loop uses `lastparamset` to schedule parameter storage after more than ten seconds, subject to the auto-commit setting and an open link. The observed interval between echo and storage command was 10.172525 seconds. This records the storage request. Physical nonvolatile storage and wear were outside the simulation. [Wire evidence](../gui-original-copter-sensors/sensors-FjBlM50a/verification.json)

## Replay

A separate isolated launch enabled Mono method tracing for the battery page. Mission Planner opened DATA and started AutoConnect. The simulator was still waiting for a connection when the readiness check timed out. No battery page was selected in that launch, so it supplies no second GUI reproduction or observed call stack. [Startup observation](startup-control/observation.log) · [Simulator log](startup-control/copter.log) · [Release log excerpt](startup-control/release-extract.txt) · [Launch script](run.sh)

From the repository root, `python -B copter-battery-page-write-study/verify.py` checks the historical raw telemetry with CRC validation, release-log order, compiled activation and timer paths, and the retained numerical results. To regenerate the IL and numeric results, run `python -B copter-battery-page-write-study/inspect_release.py` on Windows with the .NET Framework 4 compiler. It uses the checked-in Mono.Cecil library and three assemblies extracted from the pinned portable ZIP. The output identifies each assembly by SHA-256 and module version ID.
