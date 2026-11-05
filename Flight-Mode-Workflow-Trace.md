# Flight-mode selection trace

This trace covers Mission Planner 1.3.83's distributed managed library and a source-built disposable Copter SITL from ArduPilot commit `72b238201f5ea3b556e3809b2ec704fcf701474a`. The tests did not use a physical vehicle or the full Mission Planner UI.

## Source and binary

The matching-tag source `MAVLinkInterface.setMode` (`ExtLibs/ArduPilot/Mavlink/MAVLinkInterface.cs:4606`) translates a string using the current firmware's mode list. Its structure overload sends a `MAV_CMD_DO_SET_MODE` command with acknowledgement disabled, then sends legacy `SET_MODE` twice. The method returns `void`; returning from it is not confirmation that a vehicle changed mode. `translateMode` (`:6652`) compares names case-insensitively and uses `Common.getModesList` for the firmware.

For Copter, `Common.getModesList` asks `ParameterMetaDataRepository` for `FLTMODE1` options (`Common.cs:157`). The matching source's `ParameterMetaDataRepositoryAPMpdef` static constructor calls `GetMetaData()`, which can schedule downloads when cached parameter metadata is missing or old (`ExtLibs/Utilities/ParameterMetaDataRepositoryAPMpdef.cs`). Local metadata loading was tested below; download and fallback behavior were not.

In pinned ArduPilot source, the legacy message is dispatched to `handle_set_mode` and the command to `handle_command_do_set_mode`; both use `_set_mode_common` (`libraries/GCS_MAVLink/GCS_Common.cpp:2890`, `:5034`). The common handler checks the custom-mode flag and asks the vehicle to change mode. These source references are separate from the runtime observations below.

The matching-tag `FlightData.BUT_setmode_Click` handler (`GCSViews/FlightData.cs:1632`) checks the current state's failsafe flag and asks for confirmation when it is set; otherwise, or after confirmation, it passes `CMB_modes.Text` to the string mode setter. Other handlers invoke named modes including AUTO, LOITER, RTL and GUIDED. The source path has not been exercised by these library fixtures, and this observation does not establish what the UI subsequently displays.

REA's static index records four `setMode` methods (`0x06000490`–`0x06000493`) and two `translateMode` methods (`0x060004ae`–`0x060004af`) in the distributed `MissionPlanner.ArduPilot.dll`. Build-local tokens, IL hashes and static calls are recorded in `mission-planner-binary-evidence/flight-mode-method-map.json`; they are not runtime-dispatch proof.

## Packet loss in disarmed Copter SITL

The original library opened four independent disarmed Copter simulations. In each, it sent a structure requesting custom mode 4, GUIDED, after observing custom mode 0, STABILIZE. A local frame-aware relay selectively dropped mode-setting packets. The library's `setMode` call returned in every case; heartbeats were read afterward.

| Relay condition | Mode packets delivered | Final observed heartbeat |
| --- | --- | --- |
| No drop | One `DO_SET_MODE`, two `SET_MODE` | GUIDED (4), disarmed |
| Drop command | Two `SET_MODE` | GUIDED (4), disarmed |
| Drop legacy packets | One `DO_SET_MODE` | GUIDED (4), disarmed |
| Drop all three | None | STABILIZE (0), disarmed during the seven-second observation window |

Independent pymavlink decoding checked the requested mode, targets, delivered and dropped frames, and heartbeat mode/armed fields. Evidence is in `sitl-evidence/flight-mode-normal/`, `flight-mode-drop_cmd/`, `flight-mode-drop_legacy/` and `flight-mode-drop_all/`, each with `summary.json`, captures and logs. `research-tools/summarize-flight-mode.py` rechecks them. The decoder also records any non-MAVLink or malformed fragments; those bytes were forwarded by the relay. The tests show redundancy for this one disarmed mode change, not guarantees for loss, ordering, rejected modes, other vehicles, or flight.

In a separate disarmed Copter SITL run, the structure overload requested numeric custom mode 999. It returned after sending the same three packet forms. The captured `DO_SET_MODE` ACK reported `FAILED` (4), and observed heartbeats remained in disarmed STABILIZE during the seven-second post-request window. This demonstrates that returning from the void method did not itself report the simulator's rejection in this case. The test does not establish what the UI later displays. See `sitl-evidence/flight-mode-invalid/summary.json` and `research-tools/summarize-invalid-flight-mode.py`.

## String translation fixture

An in-memory test selected the source's fixed tracker mode list. With a fresh output structure, `SCAN` and `scan` both translated to target 1, base mode 1 and custom mode 2. An unknown name, an empty string and null returned false. When an output structure already contained base mode 1 and custom mode 2, the public `translateMode` method returned true for the unknown name and left those fields populated (`sitl-evidence/mode-translation-synthetic/probe.log`).

The ordinary `setMode(byte, byte, string)` source path creates a fresh structure before translation. In a separate in-memory transport capture using that setter, `not-a-mode` sent zero bytes, while `sCaN` produced one `DO_SET_MODE` and two legacy `SET_MODE` frames for target 1, base mode 1 and custom mode 2 (`string-send-summary.json` in the same evidence directory). No vehicle consumed these frames. These fixtures use the fixed tracker list, not Copter's metadata-driven list, and do not test the UI.

Two additional disarmed Copter SITL runs exercised the string setter with an original, hash-matching `MissionPlanner.ArduPilot.dll` and a test-patched `MissionPlanner.Utilities.dll` that redirects data-directory methods to `mission-planner-runtime/isolated-data`. The local Copter metadata snapshot lists `Guided` as mode 4. Both runs translated mixed-case `gUiDeD` to base mode 1/custom mode 4 and observed disarmed GUIDED heartbeats; three matching mode-setting frames were captured in each. The harness also invoked an unknown mode string before the valid one. In the second run, reflection found the loaded Copter pdef XML structurally equal to the snapshotted file, and the pdef `FLTMODE1` values matched the repository result. See `sitl-evidence/flight-mode-string/summary.json` and `flight-mode-string_verified/summary.json`. The utility assembly differs from the distributed binary, and runtime equivalence is not proven. No full UI, metadata download, fallback or physical vehicle was tested.

A separate run called the string setter with only `not-a-mode`. The relay and an independent frame decoder found no `SET_MODE` or `MAV_CMD_DO_SET_MODE` frames, while 14 captured vehicle heartbeats remained disarmed in STABILIZE. The probe observed 10 disarmed STABILIZE heartbeats during its seven-second post-call loop; the other captured heartbeats include connection and setup time. Reflection confirmed the loaded Copter pdef XML matched the saved file and supplied the chosen `FLTMODE1` values. See `sitl-evidence/flight-mode-string_invalid/summary.json` and `research-tools/summarize-invalid-flight-mode-string.py`. This used the same patched Utilities assembly and is bounded to one invalid name and a local simulator; it does not establish UI behavior or physical-aircraft behavior.
