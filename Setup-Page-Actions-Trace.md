# Setup page actions trace

Scope: using a real Mission Planner 1.3.83 setup page against a disposable ArduCopter simulator, not just drawing it. `research-tools/PageActionProbe.cs` loads the original `MissionPlanner.exe` from the data-redirected isolated copy, connects `MainV2.comPort` to a source-built Copter SITL over TCP (1,431 parameters loaded), builds the `ConfigFlightModes` page, calls `Activate()`, changes its controls, invokes the page's own private Save click handler by reflection and reads parameters back from the vehicle with `MAVLinkInterface.GetParam(name)`. The page is shown off-screen; nobody operated the window. A probe harness drives the original library; this is **not** a person clicking the live application, and it is one page and one vehicle type.

Files: `research-tools/PageActionProbe.cs`, `research-tools/run-page-action-probe.ps1`, `research-tools/page-action-sitl.sh`, `sitl-evidence/page-actions/` (CSV, status, console, simulator log).

## Result

| Step | Observation |
|---|---|
| Page opens | The six drop-downs showed the vehicle's own values (FLTMODE1..6 = 7, 9, 6, 3, 5, 0); the page and the vehicle agreed on all six. |
| Save | Requested AUTO, GUIDED, RTL, LAND, POSHOLD, BRAKE (3, 4, 6, 9, 16, 17) and ticked Simple for mode 1 and Super Simple for mode 2, then ran `BUT_SaveModes_Click`. Reading back from the vehicle: FLTMODE1..6 = 3, 4, 6, 9, 16, 17, SIMPLE = 1, SUPER_SIMPLE = 2. The button text changed to "Complete". All applied. |
| Restore | Set the original modes and unticked both boxes, saved again: FLTMODE1..6 back to 7, 9, 6, 3, 5, 0, SIMPLE = 0, SUPER_SIMPLE = 0. |

The page's save handler writes SIMPLE and SUPER_SIMPLE only when the firmware enum is `ArduCopter2` (`ConfigFlightModes.cs` around line 55 of the handler); that held for this Copter build.

## Failed attempts and what finally worked (kept on purpose)

Getting the harness to connect took about eight runs; the page result itself was the same every time the page ran (two runs, one of them against an older simulator that was still waiting, see below, plus the final reliable run).

1. The earlier runs failed with "Not Connected" from `getParamListAsync` (the stream was not open). Causes found along the way: the helper was started with `Start-Process` and a script path containing a space, which PowerShell splits (the simulator never started that way); a readiness check was fooled by a stale simulator log; inline `bash -c '...'` strings lost their double quotes in PowerShell 5.1; and a short-lived detached start behaved differently from a foreground one. One earlier "success" in this series came only because an older test simulator was still running and waiting.
2. The working shape: the simulator is a child (no `exec`) of a hidden, long-lived `wsl.exe` that runs a copy of the helper from a path without spaces, in a fresh working directory; the script waits for "Waiting for connection", sleeps 10 s, and makes one plain priming connection that reads the first 152 bytes before Mission Planner connects. I changed several things at once between the last failing and first reliable run (fresh working directory, no `exec`), so I cannot say which of the two mattered. It then worked on the first attempt.
3. The same priming behaviour was seen without Mission Planner: a plain client that connected too early got 0 bytes and the simulator exited afterwards. I did not find why; the explanation I leaned on (a premature disconnect during start-up) is a guess.

## Not covered

For the flight-modes run: the other Copter setup pages (radio calibration, accelerometer and compass calibration, motor test, frame selection; the failsafe and tuning pages are covered in the section below), any page that opens a file dialog, other vehicle types, the main flight data and planner screens, and the unmodified GUI driven by a person. In that run no message box appeared; a message box would have blocked that harness (60 s limit), because it had no message box hook (the later probe installs one).

## Parameter-bound controls on the failsafe and tuning pages

`research-tools/PageControlsProbe.cs` (run with `run-page-controls-probe.ps1`, evidence in `sitl-evidence/page-controls/`) does the same kind of check across a page: it finds every `MavlinkNumericUpDown` and `MavlinkCheckBox` bound to a parameter that exists on the vehicle, changes it by one step, waits for the page's own write path, reads the parameter back with `GetParam` and puts it back. `MavlinkComboBox` controls are listed but not changed.

| Page | Controls found | Changed | Applied | Restored |
|---|---|---|---|---|
| ConfigFailSafe | 4 numeric, 1 check box (2 combo boxes listed) | 4 + 1 | 5 | 5 |
| ConfigArducopter | 30 numeric (8 combo boxes listed) | 29 | 29 | 29 |

- The tuning page does not write when a control changes: it stages edits and writes them from its private `BUT_writePIDS_Click` handler. All 29 staged edits left the vehicle's old value in place until that handler ran (29 of 29 checked), then all were applied; setting the controls back and writing again restored them.
- The page asks "has more than doubled the last input" when a value more than doubles (it fires for parameters starting at 0). The harness answered Yes to all five prompts; they are logged in `message-boxes.txt`. `ConfigFailSafe.Activate()` also shows a props warning, logged there as well.
- The library's message box hook (`CustomMessageBox.ShowEvent`) is set by the full application at start-up. In the harness it is unset, so a message box throws an exception; the probe installs its own handler that records the text and answers Yes.

Failed attempt kept on purpose: the first controls run showed "NOT applied" for all 29 tuning controls and an exception for the failsafe page. The first was the probe's mistake (it expected an immediate write, the page stages); the second was the missing message box hook. Both were fixed in the probe, not in Mission Planner.

Not covered here: combo boxes, the other Copter pages (radio, accelerometer and compass calibration, motor test, battery monitor, frame type), pages that need real sensor or RC input, other vehicle types, and a person using the live application.
