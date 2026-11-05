# Mission Planner investigation

Updated: 5 November 2026  
Status: source, binary and simulator investigation in progress; not a complete reverse engineering of Mission Planner or ArduPilot.

## Scope and evidence

- The supplied `ardupilot-master.zip` contains the ArduPilot autopilot source tree, including vehicle firmware and libraries. It is not the Mission Planner desktop application repository.
- The separate [Mission Planner repository](https://github.com/ArduPilot/MissionPlanner) was cloned into `mission-planner-research` at commit `2fe186144802d2bb65ffa3226a5c4af12b11b07a`. The commit date is 31 October 2026. References to source lines below describe that checkout.
- The [official installer link](https://firmware.ardupilot.org/Tools/MissionPlanner/MissionPlanner-latest.msi) supplied through the project's documentation was downloaded as `mission-planner-installer.msi`. Its SHA-256 is `b3ac2f65196629514b2059344da37c1e9ccd3fe85a46c3ff88ba67a55b65e4d5`. The MSI's Property and File tables identify product version 1.3.83 and the main executable as cabinet member `_137` (file version 1.3.83.0). The source tag `MissionPlanner1.3.83`, commit `b78a7495fec69793f2fcc13be4b6a3d9e06b3e4e`, is separately available in `mission-planner-1.3.83-source`. Matching version labels do not independently prove a bit-for-bit source-to-binary correspondence.
- REA 6.8.0 was installed locally in `research-tools` and run with Node 24.22.1. Its static managed-artifact and managed-member inspections were run on an assembly extracted from the installer's cabinet. The assembly was not executed. Evidence: `mission-planner-binary-evidence/rea-ardupilot-assembly.json` and `mission-planner-binary-evidence/rea-mavlink-interface.json`.
- The MSI cabinet was extracted as an archive. Cabinet filenames are installer identifiers and need not match installed paths. The main executable and selected assemblies were inspected statically with REA. Local SITL builds and limited simulator tests were performed; an isolated, modified app copy was observed in its UI and connected through a test-only transport. No physical aircraft test was performed.

## What the two projects do

ArduPilot is the software that runs the vehicle's autopilot. Mission Planner is a ground control application used to configure the autopilot, plan missions, monitor vehicle status and review logs. The [official overview](https://ardupilot.org/planner/docs/mission-planner-overview.html) describes firmware loading, mission planning, telemetry, logs and simulation among its features. The two communicate using MAVLink, but the exact supported behavior depends on both the ground station and the autopilot version.

The Mission Planner desktop project targets .NET Framework 4.7.2 (`mission-planner-research/MissionPlanner.csproj:3`). Its README recommends Visual Studio for building on Windows. Its [installation guide](https://ardupilot.org/planner/docs/mission-planner-installation.html) describes a native Windows installer and mentions other platform variants. Platform support should be assessed per build, not inferred from the desktop project alone.

## Source architecture

The pinned 1.3.83 source tag also has a local text index at `integration-research/mission-planner-normalized-source-index.sqlite`. It contains 6,020 UTF-8 files: 2,973 matched Git blob hashes as read and 3,047 matched after CRLF-to-LF normalization. The index excludes 1,072 binary files, 133 non-UTF-8 files, 26 files over 2 MiB and one submodule link. A strict byte-match index is retained separately as `mission-planner-source-index.sqlite`. From the project folder, run `python research-tools/search-ardupilot-source.py --mission-planner MavChanged` for up to 30 FTS5 path and excerpt matches; token search does not replace reading the source or a call graph.

The following is a map of selected code, not an inventory of every feature:

| Area | Evidence | Observed responsibility |
| --- | --- | --- |
| Entry point | `Program.cs:93`, `Program.cs:491` | Starts the application and runs the `MainV2` form. |
| Application shell | `MainV2.cs:52`, `MainV2.cs:868`, `MainV2.cs:3190` | Creates and registers flight data, mission planning, configuration, simulation and help screens. |
| Connections | `MainV2.cs:1456` | Selects transport implementations, including serial, TCP, UDP and WebSocket paths, then connects the MAVLink interface. |
| MAVLink layer | `ExtLibs/ArduPilot/Mavlink/MAVLinkInterface.cs:27` | Implements packet handling and vehicle operations. The class contains parameter retrieval and setting, mission transfer and packet-reading methods. |
| Vehicle state | `ExtLibs/ArduPilot/Mavlink/MAVState.cs:23`, `ExtLibs/ArduPilot/CurrentState.cs:17` | Holds vehicle-related state and converts telemetry messages into values used by the application. |
| Flight display | `GCSViews/FlightData.cs:41` | Hosts flight-data display and log-related controls. |
| Mission planning | `GCSViews/FlightPlanner.cs:59`, `GCSViews/FlightPlanner.cs:240`, `GCSViews/FlightPlanner.cs:3963` | Manages mission, fence and rally types and mission download paths, alongside map and waypoint editing. |
| Plugins | `Plugin/PluginLoader.cs:99`, `Plugin/PluginLoader.cs:205` | Loads plugin assemblies and includes a path for compiling plugin source files. |
| Supporting libraries | `MissionPlanner.csproj:121` onward | References separate communications, mapping, MAVLink, graphics, simulation and other projects. Third-party components have their own licenses and dependencies. |

### Telemetry path

`MainV2.doConnect` selects the transport. The read loop calls `readPacketAsync`, then updates the relevant vehicle's `CurrentState` (`MainV2.cs:3064`, `MainV2.cs:3077`). `CurrentState` handles message types including `SYS_STATUS`, `ATTITUDE`, `GLOBAL_POSITION_INT`, `GPS_RAW_INT` and `VFR_HUD` (`CurrentState.cs:2944`, `:3245`, `:3261`, `:3289`, `:3844`). Flight-data bindings consume current-state values (`GCSViews/FlightData.cs:5598`). This describes the inspected source path, not timings or observed behavior of a running installation.

### Mission transfer and configuration

The planner distinguishes mission, fence and rally data (`GCSViews/FlightPlanner.cs:240`). The MAVLink interface includes mission-count and item transfer methods, retry logic and timeout handling (`MAVLinkInterface.cs:3781`, `:4000`, `:4273`). It also includes parameter-list retrieval and parameter-setting paths (`MAVLinkInterface.cs:1641`, `:1813`). MAVLink's [mission protocol](https://mavlink.io/en/services/mission.html) and [heartbeat protocol](https://mavlink.io/en/services/heartbeat.html) document the interoperability contracts. Compatibility needs testing against the intended autopilot and firmware version.

### Logs and media

`FlightData.cs:1304` accepts telemetry-log files, while other paths convert binary logs and invoke log download (`FlightData.cs:1105`, `:1215`). `MainV2.cs:3397` and nearby handlers contain GStreamer video and frame-handling paths. The exact supported codecs, live-video sources, logging formats and failures were not tested.

## REA findings

The extracted cabinet member `MissionPlanner_ArduPilot_dll` is a managed PE assembly identified by REA as `MissionPlanner.ArduPilot`, assembly version `1.0.0.0`, SHA-256 `107fa88e20dbf4c6b2e23f4a71d79030867b61cfe7b596cbc9f63b7f86187c8c`.

REA's member inspection matched `MissionPlanner.MAVLinkInterface` without an unmatched type name. It reported complete metadata coverage for that selected type. This is coverage of the selected metadata and file-backed instruction information, not proof of full behavioral reconstruction, successful decompilation, or execution. REA explicitly notes that it did not load or run the assembly, and external edge targets are not fully described by a type-scoped inspection.

The MSI File table maps `_137` to `MissionPlanner.exe`; the extracted PE SHA-256 is `a49e30e2cd635836cd737f112f419da2d3c46c59716ee08122e2986013b79f2a`. The official portable ZIP contains a byte-identical main executable. REA reports managed assembly identity `MissionPlanner`, assembly version `1.3.9384.38250`. This is a different version field from the MSI product version and file version.

The REA selected-type output for `MainV2`, `FlightData`, and `FlightPlanner` is `mission-planner-binary-evidence/rea-main-selected-members.json`: it contains 540 selected methods and 17,696 call-edge records. A whole-assembly member inspection hit REA's 64 MiB representation budget. Subsequent selected-type batches, including nested type names, cover all 890 TypeDef entries excluding `<Module>` and all 6,050 unique method tokens from the main executable's inventory. `rea-main-coverage.json` records the token-level comparison. The searchable `rea-main-index.sqlite` contains those types and methods plus 108,294 deduplicated static call anchors; its SQLite integrity check passed. Type selection coverage and static call anchors do not establish runtime execution, correct call resolution across assemblies, or full behavioral understanding.

REA's managed-artifact identity and member inspections also completed for 14 selected first-party/MAVLink/plugin DLL files; see `assemblies/manifest.json` and `assembly-members/manifest.json`. Their searchable `rea-supporting-index.sqlite` contains 2,010 type records, 13,633 method records and 64,862 deduplicated static call anchors. Its SQLite integrity check passed. Tokens are scoped to each assembly hash. This does not cover the other bundled libraries or prove runtime behavior.

An additional bounded PE-header inventory found 330 portable-distribution DLL/EXE files: 260 managed candidates and 70 other PE files. REA's managed-artifact identity check completed for all 260 managed candidates with no reported failures (`portable-binary-inventory.json` and `all-managed-identities/manifest.json`). REA export-table inspection also completed for all 70 other PE candidates (`native-exports/manifest.json`). These are identity or export-table checks; member and behavior coverage for most of those files and native-internal analysis remain incomplete.

REA's managed-native boundary inspection reported complete metadata coverage for the main executable and `MissionPlanner.Utilities.dll` (`managed-native-boundaries/manifest.json`). It identified 29 and 123 declared P/Invoke imports respectively. Utility-library module references include Windows and Linux GStreamer libraries. These are managed declarations, not proof that corresponding native libraries or exports are available or that calls execute successfully.

A separate attempt to publish a REA directory-inspection evidence bundle failed with a file-access error. It is not treated as completed evidence. Windows Installer administrative extraction did not finish; the cabinet was instead read from the MSI container and inspected as an archive. The installer was not installed through that failed attempt.

## ArduPilot source and simulator observations

The supplied archive was extracted to `ardupilot-source/ardupilot-master`. Its vehicle version headers describe ArduCopter, ArduPlane, Rover and ArduSub as 4.8.0-dev. The ZIP comment names commit `72b238201f5ea3b556e3809b2ec704fcf701474a`, and all 8,461 archived file blobs match the untruncated upstream Git tree for that commit (`ardupilot-source/archive-provenance.json`). The ZIP does not include populated Git submodule checkouts, so it is not a complete independently buildable source checkout.

In this source snapshot, `ArduCopter/Copter.cpp:971` supplies the vehicle to the HAL entry point, and `libraries/AP_Vehicle/AP_Vehicle.cpp:315` and `:577` contain the vehicle setup and loop. The Copter task table (`ArduCopter/Copter.cpp:113`) schedules sensor, controller, flight-mode, telemetry-adjacent and other tasks; `libraries/AP_Scheduler/AP_Scheduler.cpp:348` contains the scheduler loop. `libraries/GCS_MAVLink/GCS_Common.cpp:4308` and `:4387` dispatch parameter-read and mission-list messages. These are entry points for further tracing, not a complete architecture description.

The [official prebuilt SITL](https://firmware.ardupilot.org/Copter/stable/SITL_x86_64_linux_gnu/) binary reports ArduCopter 4.7.2 and source commit `fb773567896014da007bca58358704d4a0d8516f` in its accompanying `git-version.txt`. SHA-256: `caed35e4cb796ec06cac40b09566a18251771486b1cbac5e2bf16b7a5ed5045d`. This is not the 4.8.0-dev archive build.

A separate local SITL build from the verified 4.8.0-dev archive completed using pinned extracted dependency sources and copied root Git metadata; it was not built from a pristine recursive checkout. Its binary SHA-256 is `646e5b5a2d294a200dfeee25558963ca50141b6dc5c08c1dd6880607e0c35a57`. The version-matched binary passed the recorded heartbeat, telemetry, parameter-read and mission-list smoke checks (`archive-copter-smoke/results.json`) and a two-item integer mission upload/readback (`archive-copter-mission/results.json`). See `archive-linux-build-status.json` and `archive-linux-copter-build.log` for build provenance and output.

Two isolated localhost runs used `sitl-evidence/sitl_smoke.py` and `pymavlink`, with no physical aircraft. The first run received heartbeat, parameter and mission-list responses but did not receive the three telemetry streams; its result remains in `sitl-evidence/smoke-run/results.json`. The second explicitly requested telemetry and received heartbeat, `ATTITUDE`, `GLOBAL_POSITION_INT`, `SYS_STATUS`, `FRAME_CLASS`, and `MISSION_COUNT`; its result and simulator log are in `sitl-evidence/smoke-run-2`.

The mission-transfer test used a fresh isolated instance and no flight commands. An immediate upload returned `MAV_MISSION_NO_SPACE` (`mission-roundtrip/results.json`). After a startup delay, a two-item upload was accepted and count readback returned two, but the legacy float-item transfer did not reproduce the exact integer coordinates (`mission-roundtrip-2` and `mission-roundtrip-3`). A further test sent `MISSION_ITEM_INT` in response to the simulator's `MISSION_REQUEST` messages: upload, count and exact waypoint coordinate readback all passed (`mission-roundtrip-4/results.json`). These observations apply to the tested binary and client, not all firmware versions or Mission Planner.

A separate compiled harness invoked the original portable distribution's `MissionPlanner.ArduPilot.dll`, `MissionPlanner.Comms.dll` and dependencies against SITL. With the application's own .NET binding configuration, it reported `OPEN=True`, system/component `1/1` and `MISSION_COUNT=1`; output is in `sitl-evidence/missionplanner-probe/windows-probe-binding.log`, and source is `research-tools/MissionPlannerMavlinkProbe.cs`. The first harness attempt failed to load the expected `System.Memory` assembly because the harness did not yet have the application's binding configuration; that failure is retained in `windows-probe.log`. A follow-up through the original library's mission methods returned two accepted uploads, a count of two, and matching waypoint coordinates and altitude (`windows-probe-roundtrip.log`). These checks do not exercise the Mission Planner UI.

The same original-library mission round trip passed against the locally built 4.8.0-dev SITL binary (`sitl-evidence/library-exact-source/windows-probe-roundtrip.log`). Both mission items were accepted; count and waypoint coordinates matched the harness input. This tests a specific local build and mission, not the UI or every mission type.

For parameter testing, an initial `GetParam("WPNAV_SPEED")` timed out (`sitl-evidence/parameter-probe/library-parameter-test.log`). A separate read-only discovery did not receive that parameter but did receive `LOG_DISARMED` (`sitl-evidence/parameter-discovery/results.json`); this does not establish why the former was unavailable. Using a separate simulator instance and the original Mission Planner library, `LOG_DISARMED` was read as 0, set to 1, read back as 1, and restored and read back as 0. An attempt to set a name absent from the local parameter list returned false. The successful transcript is `sitl-evidence/parameter-probe/library-parameter-test-2.log`. No physical aircraft was connected. This is a single parameter path, not a complete configuration or calibration test.

A sandboxed attempt to start the unmodified portable application reached a window titled `Send Error`. A subsequent captured startup log showed that the map-cache directory under `C:\ProgramData\Mission Planner` was denied by the workspace sandbox. The window text could not be inspected because the computer-use approval timed out; no error report was submitted. A separate test copy changes the implementation of two data-directory methods in `MissionPlanner.Utilities.dll` to return a workspace path. An initial run reached screen-object creation and plugin loading; the subsequent UI tests disabled plugins. REA's comparison of the rewritten DLL reports 3,127 changed method records and 3,475 unchanged method/field records, with `cil` and `availability` differences. A separate Mono.Cecil symbolic IL comparison found two changed bodies among 3,442 methods: the two intended path methods (`cecil-symbolic-body-comparison.txt`). That narrower comparison ignores metadata token numbering and does not establish equivalence of metadata, resources, execution or every binary detail.

With plugins disabled in the isolated copy, a built-in startup script connected the application to the locally built simulator using a test-only file-backed transport and a relay restricted to localhost. The initial connection returned zero coordinates. In a fresh run the script requested telemetry, after which the application state reported the simulated position (`sitl-evidence/integrated-spool-telemetry/application-result.txt`); the relay report records traffic in both directions without errors. Later computer-use observations saw the disconnected main screens, rendered simulator telemetry, and a two-item mission read and waypoint-altitude write through this modified application and custom transport. The mission write was acknowledged and the edited altitude read back; associated home-item and radius-setting behavior is documented in `Mission-Planner-UI-Observations.md`. Those tests do not establish normal TCP or serial UI connections, functioning online map tiles, equivalence to the unmodified application, or coverage of every screen.

The current evidence map is `Reverse-Engineering-Coverage.md`. Focused traces include `Connection-Telemetry-Trace.md`, `Command-Workflow-Trace.md`, `Flight-Mode-Workflow-Trace.md`, `Mission-Transfer-Trace.md`, `Fence-Workflow-Trace.md`, `Mission-Execution-Trace.md`, `Parameter-Workflow-Trace.md`, `Accelerometer-Calibration-Trace.md`, `Log-Workflow-Trace.md`, `Map-Video-Trace.md`, `Terrain-Workflow-Trace.md`, `Firmware-Workflow-Trace.md`, `Plugin-Lifecycle-Trace.md`, `Vehicle-Mode-Failsafe-Trace.md` and `Estimator-Trace.md`. These files state the tested versions and unresolved behavior for each area. `ArduPilot-Organization-Inventory.md` lists the public repositories from a dated GitHub metadata snapshot; the listing is not a code review.

## What remains before a complete reconstruction

1. Complete the MSI identifier-to-path map and inspect the remaining assemblies. Compare the released executable against the 1.3.83 source tag while preserving any build-provenance uncertainty.
2. Inventory screens, settings, workflows, dependencies, file formats, network endpoints and plugin contracts, with source and binary references for each.
3. Trace each major workflow end to end: connection and discovery, telemetry updates, mission and fence transfer, parameter synchronization, calibration, firmware update, log processing, map providers and video.
4. Record representative UI behavior and failures in a controlled environment. Use simulator-based tests for communication and recovery, including disconnects, timeouts and incompatible versions; compare results to source and binary evidence.
5. Keep a coverage ledger recording verified features, versions, test cases, unresolved behavior and components outside scope. A feature inventory alone does not establish complete behavioral equivalence.
6. After requirements are defined, choose whether to extend Mission Planner through its plugins, fork it, or build an independent ground station using documented protocols. Evaluate license obligations and dependency licenses for the chosen distribution model.

## Licensing

The repository publishes [GPL version 3](https://github.com/ArduPilot/MissionPlanner/blob/master/COPYING.txt). Reusing or distributing a modified version can carry source and license obligations; inspect individual components and dependencies as well. An independently written implementation has different considerations. This note is not a legal determination about a future design.
