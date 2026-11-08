# Setup page state trace (Copter simulator)

Scope: what state each original Mission Planner 1.3.83 setup page is in after `Activate()` when `MainV2.comPort` is connected to a disposable ArduCopter SITL (1,431 parameters loaded). `research-tools/PageStateProbe.cs` (run with `run-page-state-probe.ps1`) builds each page from the original `MissionPlanner.exe` in the data-redirected isolated copy, calls `Activate()`, pumps events, then records `Enabled`, how many controls are enabled, how many interactive controls (buttons, combo boxes, numeric boxes, text boxes, radio and check boxes) it has and how many are enabled, and any message boxes it raised. A harness hook records message boxes and answers Yes, because the full application sets `CustomMessageBox.ShowEvent` at start-up and the harness does not. This is a probe harness, not a person using the application; it records state, not behaviour. Evidence: `sitl-evidence/page-state/` (CSV, console, message boxes, simulator log).

## Results

54 pages (those that rendered in the earlier connected run):

| Outcome | Pages |
|---|---|
| Ran and ended enabled | 40 |
| Ran and ended disabled | 8: ConfigAntennaTracker, ConfigArduplane, ConfigArdurover, ConfigAteryx, ConfigAteryxSensors, ConfigFrameType, ConfigHWESP8266, ConfigMount |
| Exception | 5: ConfigGPSOrder, ConfigPlanner, ConfigSerial, ConfigSerialInjectGPS (NullReferenceException), ConfigSimplePids (FileNotFoundException) |
| Timeout (20 s) | 1: ConfigRawParams |

Notes:

- **ConfigFrameType** is disabled, as source reading predicted: `Activate()` sets `Enabled = false` when the legacy `FRAME` parameter is absent (`ConfigFrameType.cs`). The Copter exposes `FRAME_CLASS` and `FRAME_TYPE`, and the separate `ConfigFrameClassType` page ended enabled (14 of 15 interactive controls).
- ConfigArduplane, ConfigArdurover and ConfigAntennaTracker are vehicle-specific pages and ended disabled on a Copter; I did not read their source to confirm the rule they use. ConfigMount (59 controls, all disabled) and ConfigHWESP8266 were not examined.
- The exceptions are not evidence that those pages are broken. The harness has no full application around the page (for example no main window instance). `ConfigSimplePids` failed only because `acsimplepids.xml` is looked up beside the harness executable instead of the Mission Planner folder. `ConfigRawParams` did not finish in 20 s; cause not examined.
- Message boxes: only `ConfigFailSafe` raised one ("Ensure your props are not on the Plane/Quad").
- Several pages print their own debug lines to the console (timings, "Open ... Joystick"); they are kept in `console.txt`.

## Not covered

What any page does when used (only flight modes, failsafe and tuning were exercised, see `Setup-Page-Actions-Trace.md`), the disabled pages' reasons beyond ConfigFrameType, the exceptions' causes, other vehicle types, and the unmodified GUI driven by a person.
