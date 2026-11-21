# Copter parameters in the original Mission Planner window

Mission Planner 1.3.83 ran under Mono in an isolated guest with a fresh profile and its optional startup plugins disabled. CONFIG received all 1,431 parameters from a disposable quadcopter simulator. The page previously exceeded the component harness's 20-second limit. In this application session it opened, displayed its warning, populated the grid and responded to a tree selection. The earlier timeout remains unexplained. [Release log](gui-original-copter-sensors/sensors-cQ1U0M9J/release.log) · [Capture chronology](gui-original-copter-sensors/sensors-cQ1U0M9J/observation.log)

| Operator action | Original window |
| --- | --- |
| Open CONFIG | Basic Tuning was selected. The connected Copter menu included GeoFence, Extended Tuning, MAVFtp, User Params, Full Parameter List and Planner. The Standard and Advanced Parameters entries were absent in this profile. [Screen](gui-original-copter-sensors/sensors-cQ1U0M9J/config.png) |
| Open Full Parameter List | The window tree identified the Raw Param Warning dialog. It warned that values lack min/max checks. After acknowledgement, the page displayed a category tree and a grid with name, current value, default, units, options and description columns. [Dialog tree](gui-original-copter-sensors/sensors-cQ1U0M9J/windows-list-ready.txt) · [Grid](gui-original-copter-sensors/sensors-cQ1U0M9J/list-open.png) |
| Select BATT2_MONITOR in the tree | The grid narrowed to one row. Both Value and Default showed 0, with Disabled listed for option 0. [Filtered grid](gui-original-copter-sensors/sensors-cQ1U0M9J/battery-filter.png) |
| Open User Params | The page displayed RC6_OPTION as Do Nothing and RC7_OPTION as Save WP. [Screen](gui-original-copter-sensors/sensors-cQ1U0M9J/user-params.png) |
| Open GeoFence and return to DATA | The GeoFence page displayed its controls. The return to DATA showed a disarmed quadrotor. [GeoFence](gui-original-copter-sensors/sensors-cQ1U0M9J/fence-view.png) · [DATA](gui-original-copter-sensors/sensors-cQ1U0M9J/final-hud.png) |

### Bytes received by Mission Planner

Mission Planner requested the packed parameter file with defaults over MAVFTP. The simulator's open reply advertised **17,172 bytes**. The pinned firmware calculates that estimate as the parameter count multiplied by 12. The burst-read stream returned **15,968 consecutive bytes in 146 data packets**, then signalled end-of-file at offset 15,968. The packed header and an independent decode both gave **1,431 parameters**. The UI count and the wire count agree. The shorter transfer was complete. [Firmware size calculation](ardupilot-source/ardupilot-master/libraries/AP_Filesystem/AP_Filesystem_Param.cpp#L481) · [Release source decoder](mission-planner-1.3.83-source/ExtLibs/ArduPilot/parampck.cs) · [Captured telemetry](gui-original-copter-sensors/sensors-cQ1U0M9J/2026-11-21%2019-36-45.tlog.gz)

The binary replay also checks five visible current/default pairs, including BATT2_MONITOR and ACRO_BAL_ROLL, against the packed data. All 600 captured vehicle heartbeats reported disarmed. The ground station sent zero PARAM_SET messages in this session. All 1,317 packaged release files matched after exit. [Verification script](research-tools/verify-copter-parameter-views.py) · [Archive comparison](gui-original-copter-sensors/sensors-cQ1U0M9J/archive-comparison.json)

### First connection attempt

The first guest received vehicle messages but stayed on the connecting dialog. Two CONFIG clicks and a click on Cancel left that dialog visible. The observed window did not reach a parameter page. The second guest used a fresh extraction and simulator with the same launcher. These observations do not establish why the first connection stalled. [First session screen](gui-original-copter-sensors/sensors-f0A9eZw6/cancel-connection.png) · [Window tree](gui-original-copter-sensors/sensors-f0A9eZw6/windows-cancel-connection.txt)

The two guests used the existing [isolated launcher](research-tools/observe-original-copter-sensors.sh) with `--copter`. The [review helper](gui-original-copter-sensors/review.py) collected each screen and window tree. Replay the retained evidence with `python -B research-tools/verify-copter-parameter-views.py`. Native Windows and aircraft hardware require separate observations.
