# Copter scope and remaining evidence

Saved screenshots and control trees identify the intended page after all 33 named menu selections in a modified Mission Planner 1.3.83 window. The current matrix marks 0 of those 33 page types at their original-GUI target. The pinned ArduCopter directory contributes 28 mode source files. 28 meet the matrix’s execution target. A mode request refused by the simulator can qualify as execution evidence. Successful entry and behavior require separate observations. [Coverage definitions](README.md) · [Matrix](matrix.csv)

## Work in priority order

1. Capture the release application's own connection, Copter HUD, SETUP and CONFIG navigation, then the frame, flight-mode and failsafe pages. Retain package identity, connection state, visible controls and the effect of each action.
2. Resolve differences between component activation and the connected window. Begin with CAN GPS Order, Serial Ports and RTK-GPS Inject. Record which controls the application presents with the same simulator parameters.
3. Exercise Copter workflows end to end. Match a UI action to a simulator acknowledgement, an independent readback and the state shown after reopening the page. Start with flight-mode assignments, parameter restoration and mission transfer.
4. For the remaining source-registered pages, establish which menus and controls are reachable under each relevant firmware, connection, parameter and display-setting combination. Prioritize quadcopter operation before optional peripherals and helicopter-only pages.

## Setup and configuration pages

Each source link identifies an explicit registration. Each menu link opens its saved screenshot. The review checked visible controls inside the page pane, excluding the navigation bar. All but HW ID had identifying control text. Its screenshot shows a device table with BARO1_DEVID 65540 and BARO2_DEVID 65796. CAN GPS Order showed a title and hint. FailSafe showed its controls after a warning dialog was dismissed. The two battery pages showed different controls. This establishes the page face in each capture; loading data and changing settings require their own evidence. [Per-page review and capture hashes](copter-menu-capture-review.csv) The component column records a separate harness run on Copter SITL. The harness can construct a type which the menu gates out. An enabled root control can still contain disabled children. The final column gives the current matrix level and original-GUI target status for the page across all research.
[Window capture](../sitl-evidence/live-gui-pages/pages-summary.csv) · [Component activation](../sitl-evidence/page-state/page-state.csv) · [Harness exception follow-up](../sitl-evidence/page-state-exceptions/page-state.csv)

| Page | Source registration | Quad scope or captured menu | Component | Level / GUI target |
| --- | --- | --- | --- | --- |
| Antenna.TrackerUI | [InitialSetup L333](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L333) | [Antenna Tracker](../sitl-evidence/live-gui-pages/033-Antenna-Tracker.jpg) | Enabled | L3 / open |
| ConfigAC_Fence | [SoftwareConfig L156](../mission-planner-1.3.83-source/GCSViews/SoftwareConfig.cs#L156) | Conditional or shared registration | Enabled | L3 / open |
| ConfigADSB | [InitialSetup L263](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L263) | [ADSB](../sitl-evidence/live-gui-pages/013-ADSB.jpg) | Enabled | L3 / open |
| ConfigAccelerometerCalibration | [InitialSetup L196](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L196) | [Accel Calibration](../sitl-evidence/live-gui-pages/003-Accel-Calibration.jpg) | Enabled | L3 / open |
| ConfigAdvanced | [InitialSetup L342](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L342) | Conditional or shared registration | Enabled | L3 / open |
| ConfigAntennaTracker | [InitialSetup L313](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L313), [SoftwareConfig L193](../mission-planner-1.3.83-source/GCSViews/SoftwareConfig.cs#L193) | Other firmware gate | Disabled | L3 / open |
| ConfigArducopter | [SoftwareConfig L169](../mission-planner-1.3.83-source/GCSViews/SoftwareConfig.cs#L169), [SoftwareConfig L182](../mission-planner-1.3.83-source/GCSViews/SoftwareConfig.cs#L182) | Conditional or shared registration | Enabled | L3 / open |
| ConfigArduplane | [SoftwareConfig L177](../mission-planner-1.3.83-source/GCSViews/SoftwareConfig.cs#L177) | Other firmware gate | Disabled | L3 / open |
| ConfigArdurover | [SoftwareConfig L188](../mission-planner-1.3.83-source/GCSViews/SoftwareConfig.cs#L188) | Other firmware gate | Disabled | L3 / open |
| ConfigAteryx | [SoftwareConfig L237](../mission-planner-1.3.83-source/GCSViews/SoftwareConfig.cs#L237) | Other firmware gate | Disabled | L3 / open |
| ConfigAteryxSensors | [SoftwareConfig L236](../mission-planner-1.3.83-source/GCSViews/SoftwareConfig.cs#L236) | Other firmware gate | Disabled | L3 / open |
| ConfigBatteryMonitoring | [InitialSetup L270](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L270) | [Battery Monitor](../sitl-evidence/live-gui-pages/018-Battery-Monitor.jpg) | Enabled | L3 / open |
| ConfigBatteryMonitoring2 | [InitialSetup L271](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L271) | [Battery Monitor 2](../sitl-evidence/live-gui-pages/019-Battery-Monitor-2.jpg) | Enabled | L3 / open |
| ConfigCompassMot | [InitialSetup L285](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L285) | [Compass-Motor Calibration](../sitl-evidence/live-gui-pages/022-Compass-Motor-Calibration.jpg) | Enabled | L3 / open |
| ConfigCubeID | [InitialSetup L254](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L254) | [CubeID Update](../sitl-evidence/live-gui-pages/015-CubeID-Update.jpg) | Enabled | L3 / open |
| ConfigDroneCAN | [InitialSetup L276](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L276) | [DroneCAN-UAVCAN](../sitl-evidence/live-gui-pages/020-DroneCAN-UAVCAN.jpg) | No run in this capture | L2 / open |
| ConfigESCCalibration | [InitialSetup L224](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L224) | [ESC Calibration](../sitl-evidence/live-gui-pages/008-ESC-Calibration.jpg) | Enabled | L3 / open |
| ConfigFFT | [InitialSetup L337](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L337) | [FFT Setup](../sitl-evidence/live-gui-pages/034-FFT-Setup.jpg) | Enabled | L3 / open |
| ConfigFailSafe | [InitialSetup L232](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L232) | [FailSafe](../sitl-evidence/live-gui-pages/010-FailSafe.jpg) | Enabled | L3 / open |
| ConfigFirmware | [InitialSetup L173](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L173) | Disconnected firmware installer | No run in this capture | L2 / open |
| ConfigFirmwareDisabled | [InitialSetup L169](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L169) | Connected installer placeholder | Enabled | L3 / open |
| ConfigFirmwareManifest | [InitialSetup L171](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L171) | Disconnected firmware installer | No run in this capture | L2 / open |
| ConfigFlightModes | [InitialSetup L228](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L228), [SoftwareConfig L235](../mission-planner-1.3.83-source/GCSViews/SoftwareConfig.cs#L235) | [Flight Modes](../sitl-evidence/live-gui-pages/009-Flight-Modes.jpg) | Enabled | L3 / open |
| ConfigFrameClassType | [InitialSetup L189](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L189) | [Frame Type](../sitl-evidence/live-gui-pages/002-Frame-Type.jpg) | Enabled | L3 / open |
| ConfigFrameType | [InitialSetup L188](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L188) | Legacy Copter frame selector | Disabled | L3 / open |
| ConfigFriendlyParams | [SoftwareConfig L198](../mission-planner-1.3.83-source/GCSViews/SoftwareConfig.cs#L198) | Conditional or shared registration | No run in this capture | L3 / open |
| ConfigFriendlyParamsAdv | [SoftwareConfig L203](../mission-planner-1.3.83-source/GCSViews/SoftwareConfig.cs#L203) | Conditional or shared registration | No run in this capture | L3 / open |
| ConfigGPSOrder | [InitialSetup L266](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L266) | [CAN GPS Order](../sitl-evidence/live-gui-pages/017-CAN-GPS-Order.jpg) | exception | L3 / open |
| ConfigHWAirspeed | [InitialSetup L293](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L293) | [Airspeed](../sitl-evidence/live-gui-pages/024-Airspeed.jpg) | Enabled | L3 / open |
| ConfigHWBT | [InitialSetup L321](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L321) | [Bluetooth Setup](../sitl-evidence/live-gui-pages/030-Bluetooth-Setup.jpg) | Enabled | L3 / open |
| ConfigHWCompass | [InitialSetup L206](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L206) | Alternate compass parameter set | Enabled | L3 / open |
| ConfigHWCompass2 | [InitialSetup L203](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L203) | [Compass](../sitl-evidence/live-gui-pages/004-Compass.jpg) | Enabled | L3 / open |
| ConfigHWESP8266 | [InitialSetup L329](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L329) | [ESP8266 Setup](../sitl-evidence/live-gui-pages/032-ESP8266-Setup.jpg) | Disabled | L3 / open |
| ConfigHWIDs | [InitialSetup L241](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L241) | [HW ID](../sitl-evidence/live-gui-pages/012-HW-ID.jpg) | Enabled | L3 / open |
| ConfigHWOSD | [InitialSetup L305](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L305) | [OSD](../sitl-evidence/live-gui-pages/027-OSD.jpg) | Enabled | L3 / open |
| ConfigHWOptFlow | [InitialSetup L301](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L301) | [Optical Flow](../sitl-evidence/live-gui-pages/026-Optical-Flow.jpg) | Enabled | L3 / open |
| ConfigHWPX4Flow | [InitialSetup L297](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L297) | [PX4Flow](../sitl-evidence/live-gui-pages/025-PX4Flow.jpg) | Enabled | L3 / open |
| ConfigHWParachute | [InitialSetup L325](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L325) | [Parachute](../sitl-evidence/live-gui-pages/031-Parachute.jpg) | Enabled | L3 / open |
| ConfigHWRangeFinder | [InitialSetup L289](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L289) | [Range Finder](../sitl-evidence/live-gui-pages/023-Range-Finder.jpg) | Enabled | L3 / open |
| ConfigInitialParams | [InitialSetup L237](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L237) | [Initial Tune Parameters](../sitl-evidence/live-gui-pages/011-Initial-Tune-Parameters.jpg) | Enabled | L3 / open |
| ConfigMandatory | [InitialSetup L182](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L182) | Conditional or shared registration | Enabled | L3 / open |
| ConfigMotorTest | [InitialSetup L317](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L317) | [Motor Test](../sitl-evidence/live-gui-pages/029-Motor-Test.jpg) | Enabled | L3 / open |
| ConfigMount | [InitialSetup L309](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L309) | [Camera Gimbal](../sitl-evidence/live-gui-pages/028-Camera-Gimbal.jpg) | Disabled | L3 / open |
| ConfigOSD | [SoftwareConfig L208](../mission-planner-1.3.83-source/GCSViews/SoftwareConfig.cs#L208) | Conditional or shared registration | Enabled | L3 / open |
| ConfigOptional | [InitialSetup L243](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L243) | Conditional or shared registration | Enabled | L3 / open |
| ConfigParamLoading | [InitialSetup L162](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L162), [SoftwareConfig L243](../mission-planner-1.3.83-source/GCSViews/SoftwareConfig.cs#L243), [SoftwareConfig L245](../mission-planner-1.3.83-source/GCSViews/SoftwareConfig.cs#L245) | Parameter download in progress | No run in this capture | L3 / open |
| ConfigPlanner | [SoftwareConfig L250](../mission-planner-1.3.83-source/GCSViews/SoftwareConfig.cs#L250), [SoftwareConfig L257](../mission-planner-1.3.83-source/GCSViews/SoftwareConfig.cs#L257) | Conditional or shared registration | exception | L3 / open |
| ConfigREPL | [InitialSetup L351](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L351) | Conditional or shared registration | Enabled | L3 / open |
| ConfigRadioInput | [InitialSetup L211](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L211) | [Radio Calibration](../sitl-evidence/live-gui-pages/005-Radio-Calibration.jpg) | Enabled | L3 / open |
| ConfigRadioOutput | [InitialSetup L215](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L215) | [Servo Output](../sitl-evidence/live-gui-pages/006-Servo-Output.jpg) | Enabled | L3 / open |
| ConfigRawParams | [SoftwareConfig L229](../mission-planner-1.3.83-source/GCSViews/SoftwareConfig.cs#L229) | Conditional or shared registration | timeout | L3 / open |
| ConfigSecureAP | [InitialSetup L178](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L178) | Disconnected setup | Enabled | L3 / open |
| ConfigSerial | [InitialSetup L220](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L220) | [Serial Ports](../sitl-evidence/live-gui-pages/007-Serial-Ports.jpg) | exception | L3 / open |
| ConfigSerialInjectGPS | [InitialSetup L251](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L251) | [RTK-GPS Inject](../sitl-evidence/live-gui-pages/014-RTK-GPS-Inject.jpg) | exception | L3 / open |
| ConfigSimplePids | [SoftwareConfig L164](../mission-planner-1.3.83-source/GCSViews/SoftwareConfig.cs#L164) | Conditional or shared registration | exception | L3 / open |
| ConfigTerminal | [InitialSetup L346](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L346) | Conditional or shared registration | No run in this capture | L2 / open |
| ConfigTradHeli4 | [InitialSetup L187](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L187) | Helicopter only | Enabled | L3 / open |
| ConfigUserDefined | [SoftwareConfig L221](../mission-planner-1.3.83-source/GCSViews/SoftwareConfig.cs#L221) | Conditional or shared registration | Enabled | L3 / open |
| Joystick.JoystickSetup | [InitialSetup L280](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L280) | [Joystick](../sitl-evidence/live-gui-pages/021-Joystick.jpg) | Enabled | L3 / open |
| MavFTPUI | [SoftwareConfig L215](../mission-planner-1.3.83-source/GCSViews/SoftwareConfig.cs#L215) | Conditional or shared registration | Enabled | L3 / open |
| Sikradio | [InitialSetup L259](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs#L259) | [Sik Radio](../sitl-evidence/live-gui-pages/016-Sik-Radio.jpg) | Enabled | L3 / open |

The two compass registrations depend on the presence of `COMPASS_PRIO1_ID`. The saved Copter parameter list contains it. Frame Type showed a frame-class selector. Antenna Tracker in this menu is the optional tracker UI; the firmware-gated tracker configuration page is a different type. The menu run covered the Mandatory and Optional groups. Advanced, disconnected and software-configuration pages require separate observations. Plugin-added pages are outside the explicit registration inventory. [Copter parameters](../sitl-evidence/setup-page-disabled-reasons/copter-all-parameters.csv)

## Copter mode numbers observed in the simulator

The table follows the firmware enum, including AUTO_RTL, which reports an AUTO landing sequence. The ground sweep requested modes while disarmed. A matching vehicle heartbeat establishes an active state. STABILIZE was already active at the start. A refusal below required both a rejected request and a different reported state. [Firmware enum](../ardupilot-source/ardupilot-master/ArduCopter/mode.h) · [Ground sweep](../sitl-evidence/mode-sweep/mode-sweep.csv)

The focused column uses selected airborne quad, helicopter and ground-recheck captures. A dash means that this selection supplies no further result for that mode. [Airborne quad sweep](../sitl-evidence/copter-air-modes/copter-air-modes.csv) · [Instrumented quad](../sitl-evidence/copter-untested-modes/modes-results.json) · [Turtle recheck](../sitl-evidence/copter-turtle-entry-recheck/turtle-entry.csv) · [Helicopter baseline](../sitl-evidence/heli-flight/heli-results.json) · [Configured helicopter](../sitl-evidence/heli-autorotate/heli-results.json)

The suite column gives the first matching line in each decompressed transcript. Both upstream test helpers that print `Got mode` check the vehicle-reported mode first. Those lines prove the mode was reported during the test; some tests request a mode that is already active. The line by itself gives no airborne or armed-state guarantee. [C Copter.log.gz](../sitl-evidence/autotest/Copter.log.gz) · [R Copter-rerun1.log.gz](../sitl-evidence/autotest/Copter-rerun1.log.gz) · [H Helicopter-rerun2.log.gz](../sitl-evidence/autotest-helicopter/Helicopter-rerun2.log.gz) · [Upstream heartbeat checks](../ardupilot-source/ardupilot-master/Tools/autotest/vehicle_test_suite.py)

| ID | Mode | Disarmed quad sweep | Focused captures | Suite lines |
| ---: | --- | --- | --- | --- |
| 0 | STABILIZE | Already active | heli baseline entered from AUTO | C 514, R 360, H 129 |
| 1 | ACRO | Reported active | quad entered from AUTO, heli baseline entered from AUTO | C 1641, H 1056 |
| 2 | ALT_HOLD | Reported active | quad airborne, heli baseline entered from AUTO | C 1661, R 649, H 1076 |
| 3 | AUTO | Reported active | — | C 1681, R 6316, H 1096 |
| 4 | GUIDED | Reported active | — | C 1698, R 399, H 1112 |
| 5 | LOITER | Reported active | quad airborne, heli baseline entered from AUTO | C 1772, R 888, H 1186 |
| 6 | RTL | Reported active | — | C 1840, R 1625, H 1253 |
| 7 | CIRCLE | Reported active | quad airborne | C 1851, R 24734, H 1264 |
| 9 | LAND | Reported active | — | C 1865, R 484, H 1278 |
| 11 | DRIFT | Reported active | quad airborne, quad entered from AUTO | C 1884, H 1297 |
| 13 | SPORT | Reported active | quad airborne, quad entered from AUTO | — |
| 14 | FLIP | Refused | — | R 27441 |
| 15 | AUTOTUNE | Refused | — | R 9607, H 14319 |
| 16 | POSHOLD | Reported active | quad airborne | C 2079, R 162355, H 1491 |
| 17 | BRAKE | Reported active | quad airborne | C 2148, R 16663, H 1559 |
| 18 | THROW | Reported active | — | C 2164, R 229391 |
| 19 | AVOID_ADSB | Reported active | — | C 2232, H 1573 |
| 20 | GUIDED_NOGPS | Reported active | quad entered from AUTO | C 2243, H 1584 |
| 21 | SMART_RTL | Reported active | quad airborne | C 2263, R 20178, H 1604 |
| 22 | FLOWHOLD | Refused | — | C 86398 |
| 23 | FOLLOW | Refused | — | C 2286, H 1627 |
| 24 | ZIGZAG | Reported active | — | C 185868 |
| 25 | SYSTEMID | Refused | quad entered from STABILIZE | — |
| 26 | AUTOROTATE | Refused | heli baseline refused, heli configured entered from AUTO | H 7432 |
| 27 | AUTO_RTL | Refused | — | R 7982 |
| 28 | TURTLE | Refused | quad refused, quad ground recheck active | — |

Of 26 pinned enum values, 26 were reported active in at least one of these simulator contexts. This count includes helicopter mode 26 and the reported AUTO_RTL state. Individual refusals still stand for their own configurations. Successful mode reporting alone establishes neither a completed maneuver nor the behavior of a physical aircraft.

The helicopter suite explicitly records `Got mode AUTOROTATE` at decompressed line 7432. The same passage records the numeric request for 26, the entry phase and the subsequent glide phase. The separate baseline helicopter capture shows an in-air refusal; the configured helicopter capture shows an armed transition from AUTO. These are distinct runs. A manual rotor-interlock event or a passing pre-arm test alone cannot establish a transition into mode 26.

## Modules and workflows

These modules own the principal Copter operator tasks. The remaining modules in the repository inventory span shared services, optional features and other workflows. This selection does not establish their vehicle applicability.

| Operator task | Owning module | Matrix level | GUI evidence | Target |
| --- | --- | --- | --- | --- |
| Connection and top-level navigation | [MainV2](../mission-planner-1.3.83-source/MainV2.cs) | L2 | unclaimed | open |
| Hardware setup page registration | [InitialSetup](../mission-planner-1.3.83-source/GCSViews/InitialSetup.cs) | L2 | unclaimed | open |
| Software configuration page registration | [SoftwareConfig](../mission-planner-1.3.83-source/GCSViews/SoftwareConfig.cs) | L3 | modified-copy | open |
| HUD and telemetry | [FlightData](../mission-planner-1.3.83-source/GCSViews/FlightData.cs) | L3 | modified-copy | open |
| Mission read and write | [FlightPlanner](../mission-planner-1.3.83-source/GCSViews/FlightPlanner.cs) | L3 | modified-copy | open |
| Offline log browsing | [Log](../mission-planner-1.3.83-source/Log) | L3 | modified-copy | open |
| Telemetry warning rules | [Warnings](../mission-planner-1.3.83-source/Warnings) | L3 | none | open |

The workflow rows below use the ledger’s own targets, typically executed behavior with a fault case. A met workflow target can coexist with an open original-GUI target for the owning module.

| Operator workflow | Ledger row | Fault case recorded | GUI evidence | Ledger target |
| --- | --- | --- | --- | --- |
| Connect and display telemetry | [connection-telemetry](../Connection-Telemetry-Trace.md) | yes | modified-copy | met |
| Read and write a mission | [mission-transfer](../Mission-Transfer-Trace.md) | yes | modified-copy | met |
| Pause and resume a mission | [mission-pause-restart](../Mission-Execution-Trace.md) | unclaimed | none | open |
| Read and restore parameters | [parameters-calibration](../Parameter-Workflow-Trace.md) | yes | modified-copy | met |
| Calibrate simulated accelerometers | [accelerometer-calibration](../Accelerometer-Calibration-Trace.md) | yes | none | met |
| Request and observe a mode change | [flight-mode](../Flight-Mode-Workflow-Trace.md) | yes | none | met |
| Save six switch assignments | [setup-page-action-flightmodes](../Setup-Page-Actions-Trace.md) | unclaimed | modified-copy | open |
| Read and write a fence | [fence-workflow](../Fence-Workflow-Trace.md) | yes | none | met |
| Interpret vehicle state and failsafes | [vehicle-internals](../Vehicle-Mode-Failsafe-Trace.md) | unclaimed | none | open |
| Retrieve and review flight logs | [logs](../Log-Workflow-Trace.md) | yes | modified-copy | met |
| Configure ground-station warnings | [custom-warnings](../Warnings-Engine-Trace.md) | yes | none | met |

Frame-specific and firmware evidence also lives in the [Copter frame trace](../Copter-Frame-Types-Trace.md) and [aerial execution trace](../ArduPilot-Aerial-Library-Execution-Trace.md). The mode-file count includes helicopter implementations and custom-mode support. It counts source files once and does not measure branch coverage, flight quality or aircraft behavior.

Regenerate from the repository root with `python research-tools/build-copter-scope.py` after rebuilding the coverage matrix. Use `--check` to compare the checked-in report with current inputs.
