# Execution evidence for aerial-vehicle libraries and modes (simulator flights)

This trace answers the register's open aerial items: ArduPilot libraries and two Copter modes that had only been inventoried (level 0). It uses four kinds of observation from disposable simulators of the pinned snapshot (`72b238201f5ea3b556e3809b2ec704fcf701474a`, WSL, SITL builds `arducopter`, `arducopter-heli`, `arduplane`), all flown through the prototype in `custom-gcs/`. None of this touches real hardware. "Executed" here means the code ran in a simulated flight; it does not mean the library was tested for correctness or that its behaviour on an aircraft was observed.

## How each observation was made

1. **DataFlash logs** (`research-tools/sitl-aerial-evidence.py`): a Copter and a Plane were flown through a mission with `LOG_BITMASK` 4194303 and `LOG_REPLAY` 1 set before boot. The logs were read with pymavlink's own `DFReader` (`research-tools/analyze-dataflash-log.py`, output `log-message-counts.csv`: 329 rows, per log and message type). `research-tools/map-log-messages-to-libraries.py` then searched the snapshot's source for the call that writes each message (`log-message-library-map.csv`, 118 message names, 77 credited to exactly one library directory). A message counts for a library only when the writing call is in that library's directory.
2. **STAT parameters** read before and after each flight.
3. **gdb one-shot breakpoints** (`research-tools/sitl-gdb-hits.py`): the simulator binary started under gdb with a breakpoint on each named function; the first hit prints `HIT <function>` and five stack frames (`sitl-evidence/aerial-gdb-hits/*-gdb.txt`). This is instrumented execution evidence: the function was reached in the flight, with its caller shown.
4. **Mode entry** from the log's `MODE` messages and the vehicle's reply (`mode-messages.txt`, `*.json` notes).

The raw logs (53 MB gzipped, four files) are **not committed**; `raw-log-manifest.txt` lists their names, sizes and SHA-256. The evidence in the repository is the extracts and the scripts that regenerate them.

## What was flown

- **Copter** (`copter-logged-flight`): takeoff to 15 m, two waypoints, return, automatic disarm (91 message types, 1,115,631 messages).
- **Plane** (`plane-logged-flight`): takeoff to 60 m, three waypoints, automatic landing and disarm (99 message types, 417,833 messages).
- **Helicopter** (`heli-acro`, `arducopter-heli`, frame `heli`): booted and ACRO requested; arming was refused ("Motor Interlock Enabled"), so the helicopter never flew (62 types, 565,426 messages).
- **Copter with a Lua script** (`custom-mode`): `SCR_ENABLE` 1 and `Flip_Mode.lua`, takeoff by mission, ALT_HOLD, then custom mode 100 (77 types, 545,542 messages).

## Results by library

| Library | Evidence | Limits |
|---|---|---|
| `AP_Stats` | `STAT_FLTCNT` 0 to 1, `STAT_FLTTIME` 0 to 85 s and `STAT_DISTFLWN` 0 to 303 m after the Copter flight; 0 to 62 s and 0 to 1219 m after the Plane flight; `STAT_RUNTIME` 30 s to 135 s and 111 s (`copter-logged-flight.json`, `plane-logged-flight.json`) | counters only |
| `AP_TECS` | 658 `TECS` messages in the Plane log, written at `libraries/AP_TECS/AP_TECS.cpp:1395`; breakpoint hit on `AP_TECS::update_pitch_throttle` (called from `Plane::update_alt`, stage TAKEOFF) | one flight; no other flight stage compared |
| `AP_L1_Control` | breakpoint hit on `AP_L1_Control::update_waypoint`; the Plane's `NTUN` messages (1864) carry its cross-track and bearing outputs (written by `ArduPlane/Log.cpp`, so credited to the vehicle, not the library, by the map) | only the waypoint function was instrumented, not loiter or heading modes |
| `AP_Landing` | 368 `LAND` messages written at `libraries/AP_Landing/AP_Landing_Slope.cpp:436`; breakpoint hit on `AP_Landing::verify_land`; the flight's text records "Landing approach start", the glide slope, "Flare" and a touchdown | slope landing only; the go-around ran in the earlier plane run, not in this log |
| `APM_Control` | breakpoints hit on `AP_RollController::run_axis_rate_control`, `AP_PitchController::run_axis_rate_control` and `AP_SteerController::get_steering_out_rate`; **`AP_YawController::get_rate_out` was never reached** in the flight | the yaw rate controller path was not exercised (the yaw controller's other entry points were not instrumented) |
| `AP_InertialNav` | breakpoint hit on `AP_InertialNav::update` in the Plane flight | the Copter binary has no symbol of that name; the Copter side was not examined |
| `AP_DAL` | `RFRH` 38,636, `RFRF` 38,638 and `RFRN` 394 messages in the Copter log (and in the Plane log) with `LOG_REPLAY` 1, declared at `libraries/AP_DAL/LogStructure.h:645` | the map script credited these to "not found in source" because the declaration is not in the shape it searches; the declaration line was found by a direct search; replay of the log was not attempted |
| `AP_RPM` | 3,333 `RPM` messages in the helicopter log, written at `libraries/AP_RPM/AP_RPM.cpp:241` | simulated RPM sensor on the ground; the helicopter did not fly |
| `AP_GroundEffect` | breakpoint hit on `AP_GroundEffect::update` in the Copter flight | the ground-effect compensation result was not examined |
| `AP_ICEngine` | breakpoint hit on `AP_ICEngine::update` in the Plane flight | the engine is not enabled in the simulated plane; only the periodic update ran |
| `AP_Quicktune` | breakpoint hit on `AP_Quicktune::update` in the Plane flight | quick tune is not enabled; only the periodic update ran |
| `AC_InputManager` | breakpoint hit on `AC_InputManager_Heli::get_pilot_desired_collective` in the helicopter run (STABILIZE and ACRO requested, disarmed) | the helicopter never flew; the function ran on the ground |
| `AP_Navigation` | the interface `AP_L1_Control` implements and `AP_Landing` receives (`AP_Landing::AP_Landing(..., AP_Navigation*, ...)` symbol in the binary); it has no code of its own to execute | credited through the L1 hit |
| `AP_ROMFS` | every simulator start in the repository's logs prints "Loaded defaults from @ROMFS/default_params/<frame>.parm" (1,200 lines for `copter.parm` alone in `sitl-evidence/**/*.log`) | no check of the decompression path itself |

**Not reached in these flights:** `AP_YawController::get_rate_out` (Plane; reached later, see the yaw section at the end) and `AP_LandingGear::update` (Copter; reached in the Plane build in the breakpoint sweep).

## Modes

- **`ArduCopter/mode_acro_heli.cpp`**: `ModeAcro_Heli` exists only in the helicopter build (`nm` shows 8 symbols in `arducopter-heli` and none in `arducopter`). In that build ACRO was accepted twice (disarmed and with the arm refused) and the log's `MODE` message shows mode 1 (ACRO) at 49.4 s with reason 2 (a ground-station command). The class was entered and its `run` was called by the main loop on the ground; no flight was made, so the heli-specific control (virtual flybar, acro rates) was not exercised.
- **`ArduCopter/mode_guided_custom.cpp`**: the only way into it is a script that registers a custom mode. With `Flip_Mode.lua` (mode number 100, `vehicle:register_custom_mode`), requests for mode 100 on the ground were refused by the class with the vehicle's text "Mode change to Flip 2 failed: init failed" (the mode's registered name appears in the refusal, so `ModeGuidedCustom::init` ran and returned false), and in flight from ALT_HOLD the request was accepted: the log's `MODE` messages show mode 100 at 79.6 s (reason 2) and a return to ALT_HOLD at 82.2 s (reason 32; I did not look up what that reason code means), 2.6 s later. What the script did in those 2.6 s (a flip's attitude and throttle) was not checked.

## Faults and limits

- The first version of the library map missed the `TECS` and `RFR*` writers because their declarations are multi-line or written in a shape the search did not expect; they were found by a direct search of the source and are listed above with their file and line. The map file keeps its output as generated.
- The helicopter could not be armed (motor interlock), so nothing about helicopter flight dynamics was observed.
- One flight per vehicle; the library evidence is "ran", not "ran correctly".
- The gdb runs add real-time delay only at each function's first hit; flight timing is otherwise as without gdb, but a debugger could change timing in ways I did not measure.

## Library breakpoint sweep (functions entered, three builds)

`research-tools/sitl-gdb-library-sweep.py` takes every `init`, `update`, `loop`, `read`, `run` and `setup` function of 24 inventoried classes from each simulator binary's own symbol table (`nm -C`), sets a silent continue breakpoint on each (55 in the Copter build, 64 in the Plane build, 64 in the helicopter build) and runs the simulator under gdb. `info breakpoints` after a SIGTERM gives the hit count per function (`*-hits.csv`). The runs: Copter mission (takeoff, two waypoints, return, 240 s limit), Plane mission (takeoff, three waypoints, landing, auto-disarm after 67 s), helicopter build idle with STABILIZE, ACRO, STABILIZE requested. Counts include start-up as well as flight.

**22 libraries had at least one function entered:**

| Library | Copter | Plane | Heli build |
|---|---|---|---|
| `AP_BLHeli` | `init` x1, `update` x193, `update_telemetry` x77023 | `init` x1, `update` x114, `update_telemetry` x5741 | `init` x1, `update` x54, `update_telemetry` x21237 |
| `AP_BoardConfig` | `init` x1, `init_safety` x1 | `init` x1, `init_safety` x1 | `init` x1, `init_safety` x1 |
| `AP_CANManager` | `init` x1 | `init` x1 | `init` x1 |
| `AP_CustomControl` | no symbol | `init` x1, `update` x5665 | no symbol |
| `AP_CustomRotations` | `init` x1 | `init` x1 | `init` x1 |
| `AP_EFI` | `init` x1, `update` x9627 | `init` x1, `update` x5664 | `init` x1, `update` x2654 |
| `AP_Frsky_Telem` | `init` x1 | `init` x1 | `init` x1 |
| `AP_Hott_Telem` | `init` x1 | `init` x1 | `init` x1 |
| `AP_KDECAN` | `init` x1, `update` x77022 | `init` x1, `update` x5741 | `init` x1, `update` x21237 |
| `AP_LTM_Telem` | `init` x1 | `init` x1 | `init` x1 |
| `AP_LandingGear` | `init` x1 | `init` x1, `update` x566 | `init` x1 |
| `AP_Notify` | `init` x1, `update` x9745 | `init` x1, `update` x5742 | `init` x1, `update` x2754 |
| `AP_OSD` | `init` x1 | `init` x1, `init_backend` x2 | `init` x1, `init_backend` x2 |
| `AP_OpenDroneID` | `init` x1, `update` x1925 | `init` x1, `update` x1133 | `init` x1, `update` x530 |
| `AP_RSSI` | `init` x1 | `init` x1 | `init` x1 |
| `AP_RobotisServo` | `update` x77023 | `init` x1, `update` x5741 | `init` x1, `update` x21237 |
| `AP_SBusOut` | `init` x1, `update` x77023 | `init` x1, `update` x5741 | `init` x1, `update` x21237 |
| `AP_SerialManager` | `init` x1, `init_console` x1 | `init` x1, `init_console` x2 | `init` x1, `init_console` x2 |
| `AP_Servo_Telem` | `update` x9627 | `update` x5664 | `update` x2654 |
| `AP_TempCalibration` | `update` x1925 | no symbol | `update` x530 |
| `AP_TemperatureSensor` | `init` x1, `update` x962 | `init` x1, `update` x566 | `init` x1, `update` x265 |
| `AP_VideoTX` | `init` x1, `update` x385 | `init` x1, `update` x226 | `init` x1, `update` x106 |

**Present in a binary but never entered:** `AP_PiccoloCAN`, `AP_RCTelemetry`.

**Findings worth noting**
- `AP_LandingGear::update` was never entered in the Copter run (as in the earlier sweep) and was entered 566 times in the Plane run, so the landing-gear update does run on the Plane build with default settings. `AP_LandingGear::init` ran in all three builds.
- `AP_CustomControl::init` and `AP_CustomControl::update` ran in the Plane build only (the Copter and helicopter builds have no `AP_CustomControl` symbol of that kind).
- Counts such as 77,023 for `AP_BLHeli::update_telemetry` or `AP_KDECAN::update` are the scheduler calling them at loop rate in a 240 s run; they say nothing about whether the library has anything to do.
- `AP_Radio`, `AP_IRLock` and `AP_Torqeedo` have no matching init/update/loop/read/run/setup symbol in any of the three binaries (not compiled in, or named differently), so they were not measured. `AP_PiccoloCAN` has symbols but was never entered, as were most receiver and telemetry readers (features off by default).

**Faults in this sweep.** Run 1 (`aerial-gdb-library-sweep-run1-rbreak-set-no-breakpoints`) used an `rbreak` alternation that matched nothing: 0 breakpoints, an error message only (some of its files were overwritten when a later start overlapped it). Run 2 (`aerial-gdb-library-sweep-run2-gdb-killed-by-pkill`) set the breakpoints but stopped the simulator with `pkill -f`, which also matched the gdb command line, so gdb died before it printed the hit table; its Copter log shows the breakpoints and no counts. Run 3 killed the simulator by exact name. The Copter table printed in a second layout (`<function>` instead of `in function at file:line`), which the first parser did not match, so the committed `*-hits.csv` for Copter was rebuilt from the saved gdb text with the `REPARSE=1` mode of the script (no new flight).

Limits: function entry only, three builds, default parameters, simulator only; no output of any library was examined.

## Plane yaw rate controller and a QuadPlane flight

`research-tools/sitl-plane-gaps.py` (output `sitl-evidence/plane-gaps/`), simulator and gdb only.

- **`AP_YawController::get_rate_out`** is called only when the yaw rate controller is on (`YAW_RATE_ENABLE`, an enable-flag parameter that needs a reboot to show its sub-parameters) and `ACRO_YAW_RATE` is above zero, in ACRO (`ArduPlane/mode_acro.cpp:114`) or autotune (`Attitude.cpp:541`). Both were set on a first start, the second start ran under gdb, a mission took the plane to 60 m, and ACRO was requested 60 s in. Result: `get_rate_out` was hit with the stack `ModeAcro::stabilize` (`mode_acro.cpp:114`) <- `ModeAcro::run` <- `Plane::stabilize`, desired rate 0 (no stick input in the simulator). `get_servo_out` was also hit, from `Plane::calc_nav_yaw_coordinated` (`Attitude.cpp:548`). The vehicle then took AUTO again and the mission re-ran (a second takeoff item at altitude).
- **QuadPlane flight** (`arduplane --model quadplane`, `Q_ENABLE` 1, `Q_FRAME_CLASS` 1, `Q_FRAME_TYPE` 1): mission VTOL takeoff 30 m, two waypoints at 60 m, VTOL land at home. Texts with times: waypoint item 2 begins at 13.4 s together with "Transition started airspeed 0.5"; "Transition airspeed reached 18.1" at 17.7 s; "Transition done" at 22.7 s; waypoints reached at 23.7 s and 32.2 s; then "VTOL approach", "VTOL airbrake", "VTOL position1", "VTOL position2", "Land descend started" (58.2 s), "Land final started" (95.2 s), simulator ground contact at 0.49 m/s (107.0 s), "Land complete" and automatic disarm at 114 s. All 15 breakpoints were hit: `QuadPlane::update`, `control_auto`, `motors_output`, `vtol_position_controller`, `run_z_controller`, `run_xy_controller`, `setup_target_position`, `poscontrol_init_approach`, `update_land_positioning`, `check_land_final`, `check_land_complete`, `SLT_Transition::update`, `VTOL_update`, `set_FW_roll_pitch`, and `Tiltrotor::update` (called every loop from `QuadPlane::update`, `quadplane.cpp:1778`, with no tilt motors configured). `SLT_Transition::update` is called from `QuadPlane::update` (`quadplane.cpp:1757`).
- Limits: one flight each; function entry and vehicle text only; no check of the transition quality, the airbrake distance or the landing accuracy; the Q-modes (QHOVER, QLOITER, QRTL and the rest) were entered here only by AUTO, not requested in flight; a failed or aborted transition was not tried.

## Remaining inventoried libraries: what can and cannot be reached in the simulator

Of the 22 libraries still at level 0 after the first sweep, seven have code in the Copter and Plane simulator builds (checked with `nm -C`): `RCMapper`, `AP_ExternalControl`, `AP_InternalError`, `StorageManager`, `AP_SerialLED`, `AP_JSON` and `AP_RAMTRON`. Run with `SWEEP_CLASSES` set, `research-tools/sitl-gdb-library-sweep.py` put a breakpoint on **every** function with a symbol of those classes (not only init/update/loop/read/run/setup), in one Copter and one Plane mission flight (`sitl-evidence/aerial-gdb-library-sweep-all-functions/`).

| Library | Entered | Not entered |
|---|---|---|
| `RCMapper` | constructor (1, both builds) | none other has a symbol |
| `AP_ExternalControl` | constructor (1) | `arm`, `disarm` (need external-control commands, not sent) |
| `StorageManager` | `erase` (1; the simulator starts with `-w`) | |
| `AP_JSON` | `load_json`, `parse` (1 each; the file loaded was not determined) | |
| `AP_InternalError` | | `error`, `errors_as_string`, `error_to_string` (no internal error occurred, as expected) |
| `AP_SerialLED` | | `send`, `set_RGB`, `set_num_neopixel*`, `set_num_profiled` (no serial LED configured) |
| `AP_RAMTRON` | | `init`, `read`, `write`, `send_offset` (no RAMTRON FRAM chip in the simulator) |

**Deferred, not reachable here.** These have no function symbols in either simulator binary: `AP_WindVane`, `AP_DDS` (needs the DDS build option), `AP_Module`, `AP_Menu`, `AP_CheckFirmware`, `AP_Devo_Telem`, `AP_ADC`, `AP_DAC`, `AP_IOMCU`, `AP_FlashIface`; and the `AP_HAL_ESP32`, `AP_HAL_QURT`, `AP_HAL_Empty` hardware layers, `AP_ONVIF`, and the `doc` directory are other board builds, a camera protocol or documentation. They stay at level 0, to be examined with a matching board build or hardware. This is a statement about this simulator build only: it does not show the libraries are unused.

Limits: function entry only; one flight per vehicle; default parameters; the first and second sweep attempts and the pkill/parser faults are described in the section above.
