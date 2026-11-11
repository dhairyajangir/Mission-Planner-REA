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
- **Helicopter** (`heli-acro`, `arducopter-heli`, frame `heli`): booted and ACRO requested; arming was refused ("Motor Interlock Enabled"), so the helicopter never flew in that run (62 types, 565,426 messages); a later run flew it, see the helicopter section at the end.
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

**Present in a binary but never entered:** `AP_PiccoloCAN`. `AP_RCTelemetry` was also never entered by this sweep, but see the CRSF telemetry test below: it is reachable in the simulator after all, just not by anything this sweep's two default flights did.

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

## AP_RCTelemetry/AP_CRSF_Telem: present but never entered, above, turned out to be reachable without hardware

ArduPilot ships its own SITL simulator for this (`libraries/SITL/SIM_CRSF.*`, no hardware): a UART set to a generic RC-input protocol (`--serial5=sim:crsf`, `SERIAL5_PROTOCOL` 23, read once at boot like an enable-flag parameter, so it needed the same two-stage restart used throughout this repository even though it is not one) gets fed real CRSF frames (VTX_FRAME/VTX_TELEM/VTX_UNKNOWN, 0xC8-headers) every 400 ms by the simulated device. `research-tools/sitl-crsf-telemetry-gdb.py` (output `sitl-evidence/crsf-telemetry/`) set gdb breakpoints on `AP_CRSF_Telem::AP_CRSF_Telem` (the constructor; its one call site is inside `get_singleton()`), `AP_CRSF_Telem::get_singleton`, and the decoder entry points `AP_RCProtocol_CRSF::_process_byte` and `decode_crsf_packet`, on a Copter build, and waited 50 s disarmed (`get_singleton()` only allocates `AP_CRSF_Telem` while the vehicle is not armed).

Result: the constructor was hit once, so `AP_CRSF_Telem` really was allocated at runtime; the other three breakpoints showed 0 hits even though logically something in that call chain had to run to reach the constructor. The likely explanation is that `get_singleton`, `_process_byte` and `decode_crsf_packet` are all small enough to have been inlined into their callers at this build's optimisation level, so a breakpoint on the named symbol never catches the inlined copy; this was not confirmed with a disassembly or a differently-built binary. The SITL log confirms the device attached (`SIM connection crsf:(null) on SERIAL5`) and the parameter survived the reboot (`SERIAL5_PROTOCOL=23.0`).

This resolves the sweep's never-entered finding for `AP_RCTelemetry` specifically for its CRSF backend: it is reachable in this simulator, with no hardware, using ArduPilot's own built-in test device, once the right serial port and protocol are configured. `AP_PiccoloCAN` (a CAN-bus ESC protocol with no equivalent built-in SITL simulator found) and the other two RC-telemetry backends in the same library (`AP_GHST_Telem`, `AP_Spektrum_Telem`) were not attempted here. Limits: one run, Copter only, one backend of three, entry only (no check of what telemetry data it actually sent), the three inlining-suspected breakpoints not independently confirmed.
## AP_HAL_SITL: the HAL layer every flight in this repository already runs on, confirmed by name

`AP_HAL_SITL` had never been cited in a claim of its own, despite being the HAL every single simulated flight in this repository already runs on. `research-tools/sitl-hal-sitl-gdb.py` (output `sitl-evidence/hal-sitl/`) put gdb breakpoints on `HALSITL::SITL_State::_sitl_setup` and `_fdm_input_local` (the per-loop step that advances the flight-dynamics model) over a plain Copter boot, no mission: 1 and 19,887 hits in a 20 s window once a bare MAVLink TCP connect was made.

A first attempt (kept, `sitl-evidence/hal-sitl-run1-no-connect-blocked-at-accept/`) connected nothing at all and got 0 hits on every breakpoint, including the original choice of `_fdm_input_step` (which just calls `_fdm_input_local` and was dropped after this, most likely inlined at this build's optimisation level, the same pattern as the CRSF telemetry test above). The SITL log explained it: the process was stuck at `Waiting for connection ....` on SERIAL0 — ArduPilot's own main loop does not start ticking until a GCS connects, something none of this project's other scripts had to notice because they always connect immediately as part of the test itself.

Limits: entry and call-count only, one boot, no mission, simulator only.
## AP_Vehicle: the vehicle base class every flight in this repository already runs through, confirmed by name

Same gap as AP_HAL_SITL above, one layer up: `AP_Vehicle` is the common base class every ArduPilot vehicle type inherits from, exercised by every flight in this repository, but never cited by name in a claim. `research-tools/sitl-ap-vehicle-gdb.py` (output `sitl-evidence/ap-vehicle/`) put gdb breakpoints on `AP_Vehicle::setup` and `AP_Vehicle::loop` over a plain Copter boot once a bare MAVLink TCP connect unblocked SITL's `accept()`: 1 and 25,526 hits in about a minute.

A third breakpoint, `AP_Vehicle::one_Hz_update`, could not even be set (gdb: `Function "AP_Vehicle::one_Hz_update" not defined`) - most likely inlined away entirely at this build's optimisation level, the same pattern already seen with `_fdm_input_step` and the CRSF decode functions above; not confirmed with a disassembly.

Limits: entry and call-count only, one boot, no mission, simulator only.
## Reaching the mid-flight terrain failsafe: still not reached, for a newly-understood reason

The previous section's limitation (the mid-flight failsafe remains unexercised) was followed up with `research-tools/sitl-terrain-failsafe-midflight.py` (output `sitl-evidence/terrain-failsafe-midflight/`). A first attempt (kept, `-run1-mission-based-blocked-at-prearm/`) put the terrain-relative waypoint 19 km away instead of nowhere at all, reasoning that pre-arm only checks the current/home position; it hit the identical `PreArm: waiting for terrain data` block regardless, because `AP_Arming::terrain_checks` actually requires `AP_Terrain::pre_arm_checks` to pass for every terrain-relative item already in the uploaded mission (`next_mission_index == 0`), not just the one at or near the current position. A mission-based test therefore can never reach the failsafe, near or far.

The second attempt sidestepped the mission entirely: armed in GUIDED mode with nothing uploaded (`MAV_CMD_NAV_TAKEOFF` straight into GUIDED, the same technique `sitl-guided-offboard-control.py`'s `copter_position()` uses - a live GUIDED command is never checked by `AP_Arming`), then sent one `SET_POSITION_TARGET_GLOBAL_INT` in `MAV_FRAME_GLOBAL_TERRAIN_ALT_INT` 19 km west, toward a genuinely empty neighbouring tile (home's own `S36E149.DAT` was copied in; the neighbour `S36E148.DAT`, 15 km past the tile boundary at longitude 149.0, was not - crossing into it means `AP_Terrain` opens a fresh, completely empty file there, the same shape as a real SRTM void).

The vehicle climbed and actually started flying toward the target - `TERRAIN_REPORT`'s `terrain_height` rose smoothly from 584 m (home) through 780 m and back down to 623, 636 and finally 662 m over about 164 s, a believable path over real, changing ground - and then simply stopped. For the remaining 436 s of a 600 s watch, every reading was frozen: `terrain_height` fixed at 661.57 m, `current_height` pegged at the commanded 40 m, mode staying `GUIDED` throughout, no `"Failsafe: Terrain ..."` text, no mode change to RTL. `loaded` fell from 672 to 56 while `pending` rose from 0 to 616 over the same window (the two always summed to 672), consistent with the vehicle repeatedly trying and failing to resolve the next block along the route and the cache cycling through its tracked blocks as it does.

So the vehicle neither flew into the data gap nor failed into a failsafe: it got partway there and held, for reasons this test did not dig into further (most likely `ModeGuided`'s navigation needs the next grid block resolved before advancing into it, so it stalls rather than either pressing on blind or giving up). The mid-flight terrain failsafe is still unreached by anything in this repository; reaching it now looks like it would need the vehicle's *current* position, not just its target, to be inside the gap, which this approach never achieved in 600 s. Limits: one run, Copter only, GUIDED mode only, simulator only; the stall was not investigated with gdb.
## Terrain-relative mission with no cached data at all: a permanent pre-arm block, not the mid-flight failsafe

The terrain-following section above named one thing it had not tried: a terrain data gap. `research-tools/sitl-terrain-failsafe.py` (output `sitl-evidence/terrain-failsafe/`) flew nothing, deliberately: a Copter mission with one `MAV_FRAME_GLOBAL_TERRAIN_ALT` waypoint, `TERRAIN_ENABLE` 1 (already the simulator's compiled-in default for Copter, it turns out), but the simulator's `terrain/` folder left completely empty, so the waypoint's tile is never cached and never can be, since SITL has no real tile server behind a pending request.

ArduCopter has a dedicated mid-flight terrain failsafe for missing data (`ArduCopter/events.cpp`, `failsafe_terrain_check`/`_on_event`, `FS_TERRAIN_TIMEOUT_MS` 5000: 5 s of missing data triggers `"Failsafe: Terrain data missing"` and an RTL). That path was never reached here, because something earlier caught it: `AP_Arming::terrain_checks` (`AP_Arming.cpp:1275`) requires `AP_Terrain::pre_arm_checks` to pass whenever the loaded mission `contains_terrain_alt_items()`, and that check requires `terr_pending == 0` - which never clears. The vehicle refused to arm for the full 150 s retry window, repeating `"PreArm: waiting for terrain data"` (and `"Arm: waiting for terrain data"` on each attempt). ArduPlane has the identical `terrain_checks` call (shared `AP_Arming` base), so the same pre-arm block is expected there too, though only Copter was tried.

This corrects what the test set out to show: a genuinely missing terrain tile is caught before take-off, not mid-flight, on this snapshot. The dedicated mid-flight failsafe remains unexercised by any test in this repository; reaching it would need terrain data to go missing only after a healthy start (for example deleting the tile, or an artificially large `TERRAIN_SPACING`, mid-flight), which was not attempted. Limits: Copter only, one run, simulator only, fault injection is the complete absence of a tile rather than a corrupted or partial one.
## Copter modes without an ArduPilot autotest, entered in flight

`research-tools/sitl-copter-untested-modes.py`: `coverage/copter-mode-test-map.csv` lists seven Copter modes that none of ArduPilot's own autotests names (ACRO, DRIFT, SPORT, TURTLE, SYSTEMID, GUIDED_NOGPS, AUTOROTATE). A simulated Copter was flown to 20 m by an AUTO mission with a long loiter; with RC override (sticks centred, throttle mid) each mode was requested from AUTO, held for 8 s and AUTO requested again, with one-shot gdb breakpoints on each mode's `init` and `run`.

| Mode | Answer | Reached | Notes |
|---|---|---|---|
| SYSTEMID | accepted (from STABILIZE, `SID_AXIS` 1) | `init`, `run` | text "SystemID Starting: axis=1" |
| DRIFT | accepted | `init`, `run` | run 1 without RC input: fell, ground contact 14.7 m/s |
| SPORT | accepted | `init`, `run` | |
| ACRO | accepted | `init`, `run` | |
| GUIDED_NOGPS | accepted (level attitude target streamed) | `init`, `run` | |
| TURTLE | accepted once the throttle override had reached the vehicle (see below), without gdb and under gdb, entered disarmed (text "Turtle: raise throttle to arm") | `init`, `run` | refused in the first seven attempts because of a race in my harness |
| AUTOROTATE | not tried | | helicopter build only; `ModeAutorotate` has no symbol in the Copter build |

Run history: run 1 (`copter-untested-modes-run1-no-rc-input-fell`, with the script as it ran) sent no RC input, so the Copter fell in DRIFT and ACRO and GUIDED_NOGPS were entered on the ground, disarmed; it is kept as it was. Run 2 (`copter-untested-modes`) added the RC override stream, `SID_AXIS`, a TURTLE try on the ground and the attitude stream. A third run (`copter-turtle-dshot`) set `SERVO_DSHOT_ESC` 1 for TURTLE; it was refused again with no vehicle text. `ModeTurtle::init` returns false silently when the vehicle is armed, when `enabled()` (a DShot ESC type) is false, or when a stick is off centre; `mavlink_motor_control_check` would have printed a text. **Resolved.** The earlier test `research-tools/sitl-copter-turtle-entry.py` (no debugger, `sitl-evidence/copter-turtle-entry/`) accepts TURTLE with `SERVO_DSHOT_ESC` 1 and RC channels 1 to 4 at 1500 (text "Turtle: raise throttle to arm") and it reproduced at speedups 5 and 1 (`copter-turtle-entry-recheck*`). My own harness was refused in seven attempts (six under gdb), which I first put down to gdb, then to the speedup. A bisect (`research-tools/sitl-copter-turtle-bisect.py`, `sitl-evidence/copter-turtle-bisect/`) changed one difference at a time on fresh boots (parameter written as REAL32, RC override from a thread, no data-stream request, no earlier failed attempts, `SID_AXIS`, a 60 s delay, instance 0, a full parameter download) and all of them together: all ten boots were accepted. Reading my harness showed the real difference: its override thread started with throttle 1000, and `try_mode` set the throttle to 1500 and sent the mode request in the same instant, so the vehicle judged the sticks while the throttle was still 1000 (`ModeTurtle::init` requires every stick, throttle included, at its centre) because the thread sends only every 100 ms. Adding a one-second wait after the stick change made TURTLE accepted without gdb (`copter-turtle-harness-no-gdb-throttle-settled`) and under gdb (`copter-turtle-gdb-throttle-settled`), where `ModeTurtle::init` and `ModeTurtle::run` were both hit. The failed attempts are kept. The vehicle was disarmed: arming in Turtle mode is a separate path that was not tested.

Limits: simulator only; one flight; eight seconds per mode; entry and the vehicle's texts only; the flight handling and each mode's control output were not assessed.

## ArduPlane and QuadPlane modes, requested in flight

`research-tools/sitl-plane-inflight-modes.py`: a QuadPlane simulator (`arduplane --model quadplane`, gdb attached) took off by mission (VTOL takeoff, waypoint, long loiter) and through the forward transition; with RC override (roll and pitch centred, throttle mid) each of 24 modes was requested from AUTO, held 10 s, AUTO requested again, with one-shot breakpoints on 56 `Mode<X>::_enter`/`update`/`run` functions.

| Mode | Answer | Notes |
|---|---|---|
| FLY_BY_WIRE_A | FLY_BY_WIRE_A active |  |
| FLY_BY_WIRE_B | FLY_BY_WIRE_B active |  |
| CRUISE | CRUISE active |  |
| STABILIZE | STABILIZE active |  |
| ACRO | ACRO active | The simulator reported ground contact at 13.5 m/s during the hold (no stick input beyond mid throttle). |
| MANUAL | MANUAL active | The simulator reported ground contact at 8.5 m/s during the hold. |
| TRAINING | TRAINING active | The simulator reported ground contact at 9.2 m/s during the hold. |
| CIRCLE | CIRCLE active |  |
| LOITER | LOITER active |  |
| GUIDED | GUIDED active |  |
| AVOID_ADSB | AVOID_ADSB active |  |
| TAKEOFF | TAKEOFF active | Vehicle text: "Climbing to TKOFF alt then loitering", "Takeoff level-off starting at 6m". |
| THERMAL | THERMAL refused: vehicle stays in AUTO (ack result 4) | Refused (ack result 4) with no vehicle text; no function reached; soaring was not enabled (SOAR_ENABLE not set here). |
| AUTOTUNE | AUTOTUNE active | Vehicle text: "Started autotune", "Autotuning roll pitch yaw". |
| RTL | RTL active |  |
| AUTOLAND | AUTOLAND refused: vehicle stays in AUTO (ack result 4) | Refused (ack result 4) with no vehicle text; ModeAutoLand::_enter was reached, update was not. |
| QSTABILIZE | QSTABILIZE active |  |
| QHOVER | QHOVER active |  |
| QLOITER | QLOITER active |  |
| QACRO | QACRO active | The simulator reported ground contact at 17.9 m/s during the hold. |
| QAUTOTUNE | QAUTOTUNE active | Vehicle text: "AutoTune: Started" and roll rate D messages. |
| QRTL | QRTL active | Vehicle text: "VTOL Position1 d=208.9", "VTOL Overshoot". |
| QLAND | QLAND active |  |
| LOITER_ALT_QLAND | LOITER_ALT_QLAND active |  |

Reached: 54 of 56 breakpoints. Not reached: `ModeThermal::update` (THERMAL refused, soaring not enabled) and `ModeAutoLand::update` (AUTOLAND refused after `_enter`).

Caveats: ACRO, MANUAL, TRAINING and QACRO were followed by simulator ground contact, so the plane's position and state when the next modes were requested (AUTO had recovered in between; "Transition done" appears during the CIRCLE hold) were not logged; each mode was held 10 s only; only entry and vehicle text are recorded, not flight behaviour. The earlier Plane in-flight run (`sitl-evidence/plane-modes/`) holds altitude and drift numbers for FBWA, FBWB, CRUISE, LOITER, CIRCLE, STABILIZE and GUIDED. Simulator only.

## The helicopter build in flight, and autorotation

`research-tools/sitl-heli-flight.py` (gdb, simulator only). The earlier helicopter runs could not arm: "Motor Interlock Enabled" means the motor-interlock RC switch (channel 8, `RC8_OPTION` 32 here) was high; it must be low to arm and high to run the rotor. With RC override on channel 8 low, arm in STABILIZE, then channel 8 high, the vehicle printed "RC8: MotorInterlock HIGH" and "Runup Complete" (`H_RSC_MODE` 2, `H_RSC_RUNUP_TIME` 10 s, `H_RSC_RAMP_TIME` 1 s); an AUTO mission (takeoff to 20 m, 600 s loiter) then advanced to item 2 ("Mission: 2 LoitTime").

| Mode | Answer | Reached |
|---|---|---|
| ACRO | accepted, armed after 10 s | `ModeAcro_Heli::init`, `run` |
| STABILIZE | accepted | `ModeStabilize_Heli::init`, `run` |
| ALT_HOLD | accepted | (no heli-specific breakpoint) |
| LOITER | accepted | (no heli-specific breakpoint) |
| AUTOROTATE | refused with `AROT_ENABLE` 0 (`ModeAutorotate::init` reached) | |

Motor and attitude functions hit: `AP_MotorsHeli::output_armed_stabilizing`, `AP_MotorsHeli_Single::output_to_motors`, `AC_AttitudeControl_Heli::rate_controller_run`.

**Autorotation.** The mode needs two parameters. With `AROT_ENABLE` 1 alone the vehicle refuses to arm ("PreArm: AROT: H_RSC_AROT_* not configured", from `AC_Autorotation::arming_checks`, which wants the rotor-speed controller's autorotation sub-group on); that run is kept as `heli-autorotate-run1-prearm-rsc-not-configured` (its gdb text was truncated by my own mistaken relaunch, see the NOTE file there). With `AROT_ENABLE` 1 and `H_RSC_AROT_ENBL` 1 the mode was accepted in the air; the vehicle printed "AROT: Entry Phase", "AROT: Glide Phase" and the simulator reported ground contact at 5.65 m/s; `ModeAutorotate::init` and `run` were hit (stack: `Copter::update_flight_mode`).

Limits: simulator only; one flight each; entry and vehicle text only; no altitude, rotor speed or attitude was recorded during the holds, so nothing is said about handling, the flare or the touchdown; the helicopter is the single-rotor `heli` frame only (the dual, tail and gas variants were not flown).

## AUTOLAND and THERMAL on a plain Plane

`research-tools/sitl-plane-soar-autoland.py` (gdb, simulator only). These were the two refused modes in the QuadPlane sweep.

- **AUTOLAND** (`ArduPlane/mode_autoland.cpp`): its `_enter` refuses on a QuadPlane ("autoland not available"), when not flying ("Must already be flying!"), and when the takeoff direction was not captured ("Takeoff initial direction not set"). On a plain Plane, a mission with a normal takeoff set the direction ("Autoland direction= 0"); AUTOLAND requested 40 s later was accepted and the plane flew "Loiter to alt complete", "Landing approach start at 54.6m", "Landing glide slope 8.7 degrees", "Flare 7.7m sink=2.57 speed=16.2 dist=87.4", simulator ground contact at 0.39 m/s and "Auto disarmed" (105 s). All six breakpoints hit (`_enter`, `update`, `navigate`, `check_takeoff_direction`, `landing_lined_up`, `set_autoland_direction`). One landing.
- **THERMAL** (`mode_thermal.cpp`): `_enter` returns false unless `SoaringController::is_active()`, which needs `SOAR_ENABLE` 1 (an enable flag set on a first start) and the pilot soaring switch (aux option 88) off its low position. On the Plane channel 8 is the flight-mode channel, so `RC8_OPTION` 88 made arming fail ("Arm: Mode channel and RC8_OPTION conflict"); `RC7_OPTION` 88 with channel 7 at the middle gave "Soaring: Enabled, manual mode changes". THERMAL was accepted; 2 s later the vehicle returned to AUTO with "Soaring: Reached SOAR_ALT_MIN, restoring Auto". Eleven of eleven breakpoints hit, including `init_thermalling` and `update_thermalling`. No thermal was detected or circled: the simulation has none.

Run history: run 1 held throttle at 1500 by RC override and both parts failed to arm; run 2 fixed that (AUTOLAND flew, soar still refused: RC8_OPTION conflict, pre-arm text not yet captured); run 3 captured that text; run 4 (`plane-soar`) used channel 7. All kept. Limits: simulator only; one flight each; no touchdown-position or thermal-performance measurement.

## Copter precision landing, both simulated backends

`research-tools/sitl-copter-precland.py` (gdb, simulator only). ArduPilot's own autotest `PrecisionLanding` covers the same case (`coverage/copter-mode-test-map.csv`); this run adds our own measurement. Parameters on a first start: `PLND_ENABLED` 1, `PLND_TYPE` 2 (IRLock, whose simulated sensor is `AP_IRLock_SITL`) or 4 (SITL), an analog rangefinder (`RNGFND1_TYPE` 1, scaling 10, `SIM_SONAR_SCALE` 12), `SIM_PLD_ENABLE` 1, `SIM_PLD_ALT_LMT` 15, `SIM_PLD_DIST_LMT` 10; the second start ran under gdb. The simulated landing target was placed 4 m north and 4 m west of the home position; the Copter took off in GUIDED to 9.3 m (7 to 8 s) and LAND was requested.

| Backend | Breakpoints | Vehicle text | Landed |
|---|---|---|---|
| IRLock (2) | 10 of 10: `AC_PrecLand::init`, `update`, `run_estimator`, `run_output_prediction`, `target_acquired`, `get_target_position_measurement_NED_m`, `AP_IRLock_SITL::init`, `update`, `AC_PrecLand_IRLock::init`, `update` | "PrecLand: Failsafe Measures", "PrecLand: Init Complete", "PrecLand: Target Lost" at ground contact (30 s after LAND) | 0.98 m from the target, 4.98 m from home |
| SITL (4) | 8 of 8 (the same six plus `AC_PrecLand_SITL::init`, `update`) | "PrecLand: Target Lost" at ground contact (29 s after LAND); the other two texts were not seen in this run | 0.98 m from the target, same coordinates |

The two backends ended at the same coordinates (-35.3632255, 149.1651967) to the GPS resolution; the simulation is deterministic and the target position was the same, so this is not independent evidence of each backend's accuracy. Run 1 (`copter-precland-run1-no-position-stream`) hit the same breakpoints but received no `GLOBAL_POSITION_INT`, so the distance and the climb were not measured; run 2 asked for the message at 5 Hz. Limits: simulator only; one landing per backend; a simulated target at a fixed offset; no wind; no accuracy budget; no real IRLock hardware.

## Core libraries seen in the flight logs

The log map (`log-message-library-map.csv`, 118 message types) credits 22 libraries with messages written during the simulated Copter and Plane flights. Besides the 14 libraries above, these core ones had been at level 3 only because ArduPilot's own autotests name them; the flights now give direct evidence that their log writers ran, with counts per flight in `log-message-counts.csv` (for example `AP_InertialSensor` `IMU`, `GYR`, `ACC`, `VIBE`; `AP_NavEKF3` `XKF1` to `XKF5`; `AP_NavEKF2` `NKF1` to `NKF5` in the Plane log; `AP_GPS` `GPS`, `GPA`; `AP_Baro` `BARO`; `AP_Compass` `MAG`; `AP_BattMonitor` `BAT`; `AP_AHRS` `ATT`, `POS`, `AHR2`; `AP_ESC_Telem` `ESC`, `ESCX`; `AP_Airspeed` `ARSP`; `AC_AttitudeControl` `ANG`, `RATE`, `PSCN`). Each library's claim row lists its messages and where the first writer is. A message in a log shows the code that writes it ran; it does not show that the value is right. Messages that the map could not credit to one library (`not found in source`, 33 types, and `shared`, 8 types such as the `PID*` family) are not claimed for any library.

## Estimates against the simulator's ground truth

`research-tools/analyze-sim-truth-accuracy.py` reads the saved DataFlash logs and compares the estimates the firmware wrote (`ATT`, `XKF1` for EKF3 core 0, `POS`, `BARO`, `GPS`) with the `SIM` message, which carries the simulator's true roll, pitch, yaw, latitude, longitude and altitude. Output `sitl-evidence/aerial-library-evidence/sim-truth-accuracy.csv` (whole log and airborne, per estimate and log). Airborne samples, rms error:

| Estimate | Copter flight | Plane flight | Copter + Lua script |
|---|---|---|---|
| AHRS roll (ATT) | 0.15 deg (max 0.47) | 0.30 deg (max 1.97) | 0.16 deg (max 0.22) |
| AHRS pitch (ATT) | 0.15 deg (max 0.73) | 0.22 deg (max 1.05) | 0.18 deg (max 1.26) |
| AHRS yaw (ATT) | 0.74 deg (max 1.94) | 0.55 deg (max 1.42) | 0.46 deg (max 1.63) |
| EKF3 core 0 roll (XKF1) | 0.14 deg (max 0.35) | 0.13 deg (max 0.28) | 0.16 deg (max 0.21) |
| EKF3 core 0 pitch (XKF1) | 0.12 deg (max 0.26) | 0.21 deg (max 0.45) | 0.15 deg (max 0.24) |
| EKF3 core 0 yaw (XKF1) | 0.72 deg (max 1.93) | 0.48 deg (max 0.72) | 0.47 deg (max 1.63) |
| AHRS position horizontal (POS) | 0.12 m (max 0.30) | 0.64 m (max 0.90) | 0.10 m (max 0.29) |
| AHRS altitude (POS) | 0.03 m (max 0.11) | 0.25 m (max 0.73) | 0.07 m (max 0.13) |
| barometer altitude (BARO AltAMSL) | 0.01 m (max 0.05) | 0.13 m (max 0.39) | 0.02 m (max 0.06) |
| GPS position horizontal (GPS) | 0.45 m (max 0.85) | 2.44 m (max 3.41) | 0.30 m (max 0.77) |
| GPS altitude (GPS) | 0.06 m (max 0.22) | 0.44 m (max 1.24) | 0.15 m (max 0.22) |

What this shows and does not show: in these simulations the firmware's attitude and position estimates stay within a fraction of a degree and a fraction of a metre (Copter) of the simulator's truth, with the Plane worse on position (rms 0.64 m AHRS, 2.4 m GPS) because it flies faster and the simulated GPS is the dominant error. The truth and the sensors come from the same simulator, so a shared modelling error would not show; real sensors, vibration, magnetic disturbance and wind are not represented. The helicopter log of that run has no airborne samples (it never flew in that run); a later helicopter flight is summarised in the helicopter section at the end. The ground-contact periods and the first seconds of each log are in the whole-log rows of the CSV, not here.

## Controller tracking and the simulated battery, from the logs

`research-tools/analyze-control-tracking.py` (output `sitl-evidence/aerial-library-evidence/control-tracking.csv`, simulator only): desired against actual values that the firmware logs itself, airborne samples only. All figures below are rms (max in the CSV).

| Metric | Copter flight | Plane flight | Copter + Lua script (flip) |
|---|---|---|---|
| roll, desired - actual | 0.12 deg | 11.13 deg | 0.02 deg |
| pitch, desired - actual | 0.21 deg | 2.70 deg | 0.15 deg |
| yaw, desired - actual | 0.73 deg |  | 0.07 deg |
| roll rate | 0.18 deg/s |  | 0.14 deg/s |
| pitch rate | 0.26 deg/s |  | 2.14 deg/s |
| yaw rate | 3.61 deg/s |  | 0.32 deg/s |
| altitude / height | 0.02 m | 3.56 m | 0.05 m |
| position north | 0.25 m |  | 0.12 m |
| position east | 0.28 m |  | 0.02 m |
| velocity north | 0.34 m/s |  | 0.38 m/s |
| speed demand - actual |  | 2.44 m/s |  |
| altitude error (NTUN) |  | 11.81 m |  |
| cross-track error (NTUN) |  | 18.82 m |  |
| airspeed error (NTUN) |  | 2.38 m/s |  |

Battery (`BAT`, the simulator's model): Copter flight voltage 12.196 to 12.6 V, current mean/max 25.82 / 40.75 A, remaining 100 -> 79 %; Plane flight 11.875 to 12.6 V, 11.05 / 50.00 A, 99 -> 93 %; Copter with the script 12.192 to 12.6 V, 16.68 / 41.24 A, 100 -> 92 %.

Reading these: the Copter follows its attitude, altitude and position targets closely in the simulator (the yaw rate maximum of 35 degrees per second and the script log's pitch-rate maximum of 30 are the first seconds of a turn and the flip). The Plane's large roll-demand error is the controller's lag behind step changes at each waypoint turn; its cross-track error of 19 m rms is with waypoints 250 to 300 m apart at about 22 m/s and includes the landing approach. The targets are the firmware's own, so a wrong target would not show; no wind, no sensor faults, one flight per log. The helicopter log of that run has no airborne samples; a later logged helicopter flight is summarised at the end.

## The helicopter build in a logged flight

`research-tools/sitl-heli-logged-flight.py` flew the helicopter build once with `LOG_BITMASK` 4194303: interlock low to arm, high for the rotor, an AUTO mission (takeoff to 20 m, a waypoint 40 m north with a 30 s loiter, return to launch). Texts: "Mission: 2 LoitTime" at 6.5 s, "Reached command #2" at 48.8 s, "Mission: 3 RTL", "SIM Hit ground at 0.50 m/s" at 95.7 s, "Disarming motors" at 107.6 s. `STAT_FLTCNT` 0 to 1, `STAT_FLTTIME` 0 to 101 s, `STAT_DISTFLWN` 0 to 116 m. The raw log (62 MB, 32 MB gzipped) is listed with its checksum in `raw-log-manifest.txt` and not committed. The two analyses above were run on it (`sim-truth-accuracy-heli.csv`, `control-tracking-heli.csv`), airborne samples, rms:

| Estimate or tracking | Helicopter |
|---|---|
| AHRS roll (ATT) against truth | 0.09 deg (max 0.29) |
| AHRS pitch (ATT) against truth | 0.11 deg (max 0.32) |
| AHRS yaw (ATT) against truth | 2.45 deg (max 9.51) |
| EKF3 core 0 yaw (XKF1) against truth | 2.45 deg (max 9.50) |
| AHRS position horizontal (POS) against truth | 0.07 m (max 0.23) |
| barometer altitude (BARO AltAMSL) against truth | 0.14 m (max 0.31) |
| GPS position horizontal (GPS) against truth | 0.24 m (max 0.80) |
| roll: desired - actual (ANG) | 0.19 deg (max 0.89) |
| pitch: desired - actual (ANG) | 0.29 deg (max 1.49) |
| yaw: desired - actual (ANG) | 3.46 deg (max 17.06) |
| yaw rate: desired - actual (RATE) | 15.10 deg/s (max 83.11) |
| altitude: desired - actual (CTUN DAlt - Alt) | 0.04 m (max 0.16) |
| position north: target - actual (PSCN) | 0.12 m (max 0.45) |
| position east: target - actual (PSCE) | 0.18 m (max 0.69) |

The helicopter's roll, pitch, position and altitude are as close as the Copter's, but its yaw is looser: 2.4 degrees rms against the truth (the Copter 0.7) and a yaw-rate error of 15 degrees per second rms (the Copter 3.6), with up to 83 degrees per second at its worst. The simulated battery sits at about 50 V. The helicopter flew with the single-rotor `heli` frame only; the other variants were flown later, see the helicopter frame variants section at the end. Simulator only, one flight, the firmware's own targets.

## Helicopter frame variants

`research-tools/sitl-heli-variants.py` started `arducopter-heli` with each variant's model name and default-parameter files from `Tools/autotest/pysim/vehicleinfo.json` (`heli-gas`, `heli-ddvptail`, `heli-ddfptail`, `heli-dual`, `heli-blade360`, `heli-quad`) plus a one-line file setting `LOG_BITMASK` 4194303, and flew the mission of the single-rotor flight above: interlock switch low to arm and high to run (channel 8, by RC override), an AUTO mission (takeoff to 20 m, 30 s loiter at a waypoint 40 m north, return to launch). ArduPilot's own `FlyEachFrame` test lists every helicopter frame as known broken ("wrong binary, different takeoff regime"), because it starts the Copter binary; here the helicopter binary was used. All six armed, flew, touched down at 0.49 to 0.50 m/s and disarmed on their own. The frame parameters read back confirm each model: `FRAME_CLASS` 6 (single rotor) for the gas, tail and blade360 variants, 11 for the dual rotor, 13 for heli-quad, and `H_TAIL_TYPE` 2 and 3 for the direct-drive tails. Airborne rms, from the logs:

| Variant | Frame class | Tail type | Flight time | AHRS roll (deg) | AHRS pitch (deg) | AHRS yaw (deg) | AHRS position (m) | baro altitude (m) | GPS position (m) | roll tracking (deg) | pitch tracking (deg) | yaw tracking (deg) | yaw rate (deg/s) | altitude tracking (m) | position N tracking (m) | position E tracking (m) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| heli-gas | 6 | 0 | 101 s | 0.10 | 0.11 | 2.46 | 0.07 | 0.12 | 0.24 | 0.20 | 0.28 | 3.26 | 14.80 | 0.04 | 0.12 | 0.19 |
| heli-ddvptail | 6 | 2 | 101 s | 0.09 | 0.11 | 2.44 | 0.07 | 0.12 | 0.24 | 0.19 | 0.29 | 3.43 | 14.97 | 0.04 | 0.12 | 0.18 |
| heli-ddfptail | 6 | 3 | 101 s | 0.08 | 0.10 | 2.05 | 0.07 | 0.12 | 0.24 | 0.27 | 0.58 | 7.27 | 21.43 | 0.04 | 0.12 | 0.18 |
| heli-dual | 11 |  | 103 s | 0.10 | 0.12 | 2.96 | 0.07 | 0.12 | 0.24 | 0.81 | 1.02 | 9.90 | 29.57 | 0.04 | 0.18 | 0.10 |
| heli-blade360 | 6 | 0 | 101 s | 0.09 | 0.11 | 2.59 | 0.07 | 0.12 | 0.25 | 2.46 | 0.33 | 2.62 | 14.49 | 0.03 | 0.13 | 0.38 |
| heli-quad | 13 |  | 102 s | 0.09 | 0.11 | 2.93 | 0.07 | 0.12 | 0.24 | 0.34 | 0.46 | 2.79 | 13.57 | 0.01 | 0.34 | 0.04 |

Reading these: the estimates against the truth are almost the same in all six (roll and pitch about 0.1 degree, yaw 2.0 to 3.0 degrees, AHRS position 0.07 m, barometer 0.12 m, GPS 0.24 m), because the simulated sensors and the estimator do not depend on the frame. The controller tracking is where they differ: the dual rotor has the largest roll and pitch tracking error (0.8 and 1.0 degrees rms against 0.2 to 0.3 for the single rotor) and the largest yaw-rate error (30 degrees per second); the fixed-pitch direct-drive tail has the loosest yaw (7.3 degrees rms, 21 degrees per second against 3.3 and 15 for the gas frame); blade360 shows a 2.5 degree rms roll error and 10 degrees per second roll-rate error with the biggest east position error (0.38 m); heli-quad has the smallest altitude error (0.01 m) and the largest north position error (0.34 m). One flight each, so these are observations of this mission, not a ranking, and the cause of any difference (frame tuning in the default parameters, the simulator model, or the mission geometry) was not investigated. The raw logs (six, about 30 MB gzipped each) are not committed; their checksums are in `raw-log-manifest.txt`.

## Plane and QuadPlane airframe variants

`research-tools/sitl-plane-variants.py` started `arduplane` for each frame of `Tools/autotest/pysim/vehicleinfo.json` that the simulator can fly itself (the model name and default-parameter files listed there, plus a file setting `LOG_BITMASK` 4194303) and flew one mission: plain planes an automatic takeoff to 60 m, three waypoints and an automatic landing; VTOL types a VTOL takeoff to 30 m, two waypoints at 60 m and a VTOL landing. Each was armed in MANUAL, set to AUTO and followed to disarm or 300 s. The frame parameters read back confirm the configuration (`Q_FRAME_CLASS` 7 for the tri, tilt-tri, tilt-tri-vectored and CL-84 frames, 1 for tilt, tilt-vectored, ICE and the copter tailsitter, 5 for the firefly, 10 for the plane tailsitter).

| Variant | Kind | Q_FRAME_CLASS | Result | Flight time | Note |
|---|---|---|---|---|---|
| plane | plane |  | completed, disarmed | 64 s |  |
| plane-elevon | plane |  | completed, disarmed | 63 s |  |
| plane-vtail | plane |  | completed, disarmed | 63 s |  |
| plane-jet | plane |  | completed, disarmed | 70 s |  |
| plane-dspoilers | plane |  | completed, disarmed | 62 s |  |
| plane-ice | plane |  | did not complete | 0 s | armed and AUTO accepted ("Triggered AUTO"), then no takeoff for 300 s (flight time 0); no vehicle text said why; ArduPilot's own `FlyEachFrame` test skips this frame as "ICE engine needs starting; different takeoff regime", which explains it; with the start switch held (RC channel 11) it flew, see below |
| plane-3d | plane |  | completed, disarmed | 60 s |  |
| quadplane-tri | vtol | 7 | completed, disarmed | 110 s |  |
| quadplane-tilt | vtol | 1 | completed, disarmed | 114 s |  |
| quadplane-tilttri | vtol | 7 | completed, disarmed | 112 s |  |
| quadplane-tilttrivec | vtol | 7 | completed, disarmed | 112 s |  |
| quadplane-tilthvec | vtol | 1 | completed, disarmed | 178 s |  |
| quadplane-cl84 | vtol | 7 | completed, disarmed | 110 s |  |
| quadplane-ice | vtol | 1 | did not complete | 287 s | VTOL takeoff and transition started, but forward flight was very slow: waypoint 2 reached at 200 s, the VTOL landing approach began at 233 s, not landed at the 300 s limit; ArduPilot's own test skips this frame with the same reason ("ICE engine needs starting; different takeoff regime"), and with the start switch held it completed in 113 s, see below |
| quadplane-copter_tailsitter | vtol | 1 | did not complete | 282 s | VTOL takeoff printed "Transition VTOL done"; no further mission progress for 282 s of flight time; ArduPilot's own `FlyEachFrameRCInput` skips this frame as "tailsitter hover regime; nose-up attitude", but its `FlyEachFrame` flies it after an extra reboot; with that reboot it completed, see below |
| plane-tailsitter | vtol | 10 | did not complete | 286 s | VTOL takeoff, "Transition FW done, roll error", then repeated simulator ground contacts (4 to 12 m/s) until the 300 s limit; ArduPilot's own test skips this frame as "unstable in hover; unflyable in cruise" |
| firefly | vtol | 5 | completed, disarmed | 110 s |  |

Airborne rms against the simulator truth (AHRS columns) and against the firmware's own targets (demand columns); angles in degrees:

| Variant | AHRS roll | AHRS pitch | AHRS yaw | AHRS pos (m) | GPS pos (m) | roll demand (deg) | pitch demand (deg) | height (m) | speed (m/s) | cross-track (m) |
|---|---|---|---|---|---|---|---|---|---|---|
| plane | 0.30 | 0.23 | 0.53 | 0.61 | 2.36 | 11.18 | 2.98 | 3.62 | 2.50 | 19.00 |
| plane-elevon | 0.29 | 0.25 | 0.54 | 0.61 | 2.37 | 12.58 | 5.09 | 3.98 | 2.37 | 17.88 |
| plane-vtail | 0.31 | 0.24 | 0.55 | 0.61 | 2.37 | 11.04 | 4.68 | 3.98 | 2.33 | 18.34 |
| plane-jet | 2.28 | 0.46 | 0.73 | 1.30 | 5.05 | 19.59 | 6.13 | 19.87 | 13.44 | 209.95 |
| plane-dspoilers | 0.29 | 0.24 | 0.54 | 0.63 | 2.43 | 12.20 | 4.29 | 4.00 | 2.30 | 17.72 |
| plane-ice (incomplete) | - | - | - | - | - | - | - | - | - | - |
| plane-3d | 0.33 | 0.13 | 0.24 | 0.00 | 2.63 | 13.56 | 4.42 | 5.20 | 5.25 | 9.96 |
| quadplane-tri | 0.24 | 0.16 | 0.92 | 0.23 | 1.51 | 9.77 | 2.76 | 3.32 | 11.24 | 16.34 |
| quadplane-tilt | 0.24 | 0.17 | 0.79 | 0.22 | 1.46 | 9.76 | 2.52 | 3.45 | 11.68 | 18.27 |
| quadplane-tilttri | 0.23 | 0.16 | 0.75 | 0.22 | 1.48 | 9.75 | 2.86 | 3.70 | 11.51 | 17.28 |
| quadplane-tilttrivec | 0.27 | 0.15 | 0.78 | 0.23 | 1.51 | 7.65 | 2.12 | 3.68 | 11.41 | 16.83 |
| quadplane-tilthvec | 0.26 | 0.17 | 0.44 | 0.19 | 1.25 | 7.01 | 2.67 | 15.28 | 12.15 | 6.81 |
| quadplane-cl84 | 0.28 | 0.19 | 0.42 | 0.23 | 1.57 | 9.88 | 4.65 | 5.04 | 11.77 | 17.01 |
| quadplane-ice (incomplete) | 0.09 | 0.09 | 1.73 | 0.09 | 0.32 | 1.59 | 0.34 | 14.58 | 20.91 | 3.10 |
| quadplane-copter_tailsitter (incomplete) | - | - | - | - | - | - | - | - | - | - |
| plane-tailsitter (incomplete) | 39.44 | 19.23 | 38.20 | 0.66 | 0.81 | 105.69 | 41.46 | 41.97 | 8.48 | 47.45 |
| firefly | 0.23 | 0.16 | 0.77 | 0.23 | 1.53 | 12.21 | 3.85 | 4.31 | 11.66 | 17.89 |

Reading these: the AHRS columns are almost the same for every airframe that flew, as for the helicopter frames: the estimator does not depend on the frame. The tracking columns differ. The standard, elevon, V-tail and spoiler frames track alike (height 4.0 m, speed 2.3 m/s, cross-track 18 m rms). The jet has the largest errors (height 20 m, speed 13 m/s, cross-track 210 m with a maximum of 545 m): at jet speed the waypoints 250 to 300 m apart are passed in a few seconds and the turns are wide. The 3D frame cross-track is tighter (10 m), but its AHRS position error comes out as 0.00 m rms because the frame's own parameter file (`models/plane-3d.parm`) sets `AHRS_EKF_TYPE` 10, the simulator-state AHRS, which hands the simulator's true state to the vehicle: its AHRS columns say nothing about the estimator and must not be compared with the others (the `POS` messages equal the `SIM` truth exactly in that log); the jet's AHRS roll error is also larger than the others (2.3 degrees rms); the tilt-vectored QuadPlane has a 15 m rms height error against 3 to 5 m for the other VTOL frames. The VTOL frames include the vertical phases in the airborne window, so their height and speed errors are not comparable with the plain planes. The four incomplete flights are in the table for completeness and their figures should not be compared; their causes match ArduPilot's own list of known-broken frames in `FlyEachFrameRCInput` (`ArduPlane` autotest: `plane-ice` and `quadplane-ice` "ICE engine needs starting; different takeoff regime", `plane-tailsitter` "unstable in hover; unflyable in cruise", `quadplane-copter_tailsitter` "tailsitter hover regime; nose-up attitude"); the two ICE frames completed once the engine-start switch was held (see the ICE section below) and the copter-tailsitter completed after the extra reboot ArduPilot's own `FlyEachFrame` uses (see the tailsitter section); `plane-tailsitter` still fails, as ArduPilot's list says. One flight each. The raw logs (seventeen, 7 to 30 MB gzipped) are not committed; their checksums are in `raw-log-manifest.txt`.

## The ICE frames with the engine started

The ICE frames' parameter file (`default_params/plane-ice.parm`) sets `RC11_OPTION` 179 (ICE start/stop), and `AP_ICEngine` starts the engine when the start channel is at or above 1700. `sitl-plane-variants.py` with `ICE_START_CH11=1` (MAVLink 2, RC override with channel 11 at 1900 for the whole flight) flew both frames again (`sitl-evidence/plane-variants-ice-started/`):

- **plane-ice**: "Engine running" 2.2 s after the takeoff began, takeoff level-off at 20 m, takeoff complete at 60.7 m, landing approach at 39 s, automatic disarm at 68.9 s; `STAT_FLTTIME` 63 s. Without the switch the same plane armed, was set to AUTO and never left the ground in 300 s.
- **quadplane-ice**: "Starting engine", the simulator's `SIM_ICEngine` messages (`starter:1`, then "Engine started", "Engine running" at 3.2 s), a VTOL mission that completed with disarm at 113.3 s; `STAT_FLTTIME` 110 s. Without the switch it was still airborne at 300 s, having reached waypoint 2 at 200 s.

Accuracy and tracking (rms, airborne): plane-ice AHRS roll 0.30, pitch 0.23, yaw 0.52 deg, AHRS position 0.64 m, GPS position 2.44 m, height demand error 3.53 m, speed error 2.45 m/s, cross-track 19.01 m; quadplane-ice AHRS roll 0.24, pitch 0.16, yaw 0.90 deg, AHRS position 0.23 m, height 3.30 m, speed 11.23 m/s, cross-track 16.59 m. The engine was started by the RC switch the parameter file prescribes; the start-up delay, the starter time and the engine's model were not examined. This resolves the two ICE failures above; the two tailsitters stay unresolved, and ArduPilot itself does not fly them in its frame test.

## The tailsitters with the extra reboot

ArduPilot's `FlyEachFrame` (ArduPlane autotest) lists only `plane-tailsitter` as known broken ("unstable in hover; unflyable in cruise") and flies `quadplane-copter_tailsitter` with a step my sweep lacked: "tailsitter needs extra re-boot to pick up the rotated AHRS view" (the simulator is restarted once, without wiping, when `Q_TAILSIT_ENABLE` is 1). `sitl-plane-variants.py` with `TAILSITTER_REBOOT=1` does the same (`sitl-evidence/plane-variants-tailsitter-reboot/`):

- **quadplane-copter_tailsitter** (`Q_TAILSIT_ENABLE` 1, `Q_FRAME_CLASS` 1): completed. VTOL takeoff, "Angle assist r=2 p=85" at 14.3 s, "Transition FW done" at 16.7 s, waypoints reached at 23.9 and 32.1 s, "VTOL approach", "Transition VTOL done, timeout" at 48.8 s, a "VTOL Overshoot" and a longer landing sequence ("Land final started" at 147.6 s), simulator ground contact at 0.43 m/s, "Land complete" and automatic disarm at 165.8 s; `STAT_FLTTIME` 163 s. Without the reboot the same frame hovered with no mission progress for 282 s. Accuracy against the truth (rms): AHRS roll 77.44, pitch 77.64, yaw 78.69 deg, AHRS position 0.22 m; tracking: roll demand 77.87 deg, pitch demand 6.79 deg, height 25.41 m, speed 11.96 m/s, cross-track 13.66 m.
- **plane-tailsitter** (`Q_FRAME_CLASS` 10, `Q_FRAME_TYPE` 1): still failed with the reboot, as ArduPilot's list says it should: VTOL takeoff, "Transition FW done" at 15.8 s, then simulator ground contacts (146 of them) until the 300 s limit.

So the copter-tailsitter failure in the airframe sweep came from my sweep missing a start-up step that ArduPilot's own test performs, not from the frame; why the rotated AHRS view needs a reboot was not investigated here. The plane-tailsitter remains unexplained beyond ArduPilot's note. One flight each, simulator only.

## All multicopter frames

`research-tools/sitl-copter-variants.py` started `arducopter` for each of the 28 internal frames of `Tools/autotest/pysim/vehicleinfo.json` that need neither an external simulator nor a CAN peripheral (model name and default-parameter files from there, plus a file setting `LOG_BITMASK` 4194303) and flew one mission, armed in STABILIZE, then AUTO with `MAV_CMD_MISSION_START` (takeoff to 20 m, a waypoint 40 m north with a 30 s loiter, return to launch). All 28 armed, flew and disarmed on their own. The first sweep could not arm the three `FRAME_CLASS` 15 (dynamic matrix) frames, `dotriaconta_octaquad_x`, `hexadeca-octa` and `hexadeca-octa-cwx`: the vehicle said "Motors: Check frame class and type". They need the Lua motor-matrix example script of the frame (`MotorMatrix_*.lua`, named by `frame_example_script` in `vehicleinfo.json`), `SCR_ENABLE` 1 and a restart, which ArduPilot's own `FlyEachFrame` does; with `SCRIPTED_FRAMES=1` they flew (`sitl-evidence/copter-variants-scripted/`). Airborne rms; angles in degrees:

| Frame | Class | Type | Flight time | AHRS roll | AHRS pitch | AHRS yaw | AHRS pos (m) | roll trk | pitch trk | yaw trk | alt trk (m) | pos N trk (m) | pos E trk (m) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| + | 1 | 0 | 99 s | 0.13 | 0.11 | 0.58 | 0.06 | 0.01 | 0.03 | 0.04 | 0.02 | 0.16 | 0.02 |
| X | 1 | 1 | 99 s | 0.13 | 0.11 | 0.58 | 0.06 | 0.01 | 0.02 | 0.04 | 0.02 | 0.16 | 0.02 |
| bfx | 1 | 12 | 99 s | 0.13 | 0.11 | 0.58 | 0.06 | 0.01 | 0.02 | 0.04 | 0.02 | 0.16 | 0.02 |
| djix | 1 | 13 | 99 s | 0.13 | 0.11 | 0.58 | 0.06 | 0.01 | 0.02 | 0.04 | 0.02 | 0.16 | 0.02 |
| cwx | 1 | 14 | 99 s | 0.13 | 0.11 | 0.58 | 0.06 | 0.01 | 0.02 | 0.04 | 0.02 | 0.16 | 0.02 |
| hexa | 2 | 0 | 99 s | 0.13 | 0.11 | 0.58 | 0.06 | 0.01 | 0.03 | 0.04 | 0.02 | 0.16 | 0.02 |
| hexax | 2 | 1 | 99 s | 0.13 | 0.11 | 0.58 | 0.06 | 0.01 | 0.02 | 0.04 | 0.02 | 0.16 | 0.02 |
| hexa-cwx | 2 | 14 | 99 s | 0.13 | 0.11 | 0.58 | 0.06 | 0.01 | 0.02 | 0.04 | 0.02 | 0.16 | 0.02 |
| hexa-dji | 2 | 13 | 99 s | 0.13 | 0.11 | 0.58 | 0.06 | 0.01 | 0.02 | 0.04 | 0.02 | 0.16 | 0.02 |
| octa | 3 | 0 | 99 s | 0.13 | 0.11 | 0.58 | 0.06 | 0.01 | 0.03 | 0.04 | 0.02 | 0.16 | 0.02 |
| octa-dji | 3 | 13 | 99 s | 0.13 | 0.11 | 0.58 | 0.06 | 0.01 | 0.03 | 0.04 | 0.02 | 0.16 | 0.02 |
| octa-cwx | 3 | 14 | 99 s | 0.13 | 0.11 | 0.58 | 0.06 | 0.01 | 0.03 | 0.04 | 0.02 | 0.16 | 0.02 |
| octa-quad | 4 | 0 | 99 s | 0.13 | 0.11 | 0.58 | 0.06 | 0.02 | 0.01 | 0.08 | 0.01 | 0.16 | 0.02 |
| octa-quad-cwx | 4 | 14 | 99 s | 0.13 | 0.11 | 0.58 | 0.06 | 0.02 | 0.01 | 0.08 | 0.01 | 0.16 | 0.02 |
| octa-quad-cor | 4 | 20 | 99 s | 0.13 | 0.11 | 0.58 | 0.06 | 0.01 | 0.01 | 0.03 | 0.02 | 0.16 | 0.02 |
| octa-quad-cw-cor | 4 | 21 | 99 s | 0.13 | 0.11 | 0.58 | 0.06 | 0.01 | 0.01 | 0.03 | 0.02 | 0.16 | 0.02 |
| deca | 14 | 0 | 99 s | 0.13 | 0.11 | 0.58 | 0.06 | 0.02 | 0.03 | 0.10 | 0.02 | 0.16 | 0.02 |
| deca-cwx | 14 | 14 | 99 s | 0.13 | 0.11 | 0.58 | 0.06 | 0.02 | 0.03 | 0.10 | 0.02 | 0.16 | 0.02 |
| tri | 7 | 0 | 99 s | 0.12 | 0.10 | 0.57 | 0.06 | 0.04 | 0.02 | 0.35 | 0.02 | 0.16 | 0.02 |
| y6 | 5 | 0 | 99 s | 0.13 | 0.11 | 0.58 | 0.06 | 0.01 | 0.03 | 0.04 | 0.02 | 0.16 | 0.02 |
| dodeca-hexa | 12 | 0 | 99 s | 0.13 | 0.11 | 0.58 | 0.06 | 0.03 | 0.03 | 0.10 | 0.02 | 0.16 | 0.02 |
| dotriaconta_octaquad_x | 15 | 0 | 99 s | 0.14 | 0.12 | 0.61 | 0.05 | 0.01 | 0.02 | 0.04 | 0.01 | 0.16 | 0.02 |
| hexadeca-octa | 15 | 0 | 99 s | 0.14 | 0.12 | 0.60 | 0.06 | 0.02 | 0.03 | 0.10 | 0.01 | 0.16 | 0.02 |
| hexadeca-octa-cwx | 15 | 0 | 99 s | 0.14 | 0.12 | 0.60 | 0.06 | 0.03 | 0.02 | 0.10 | 0.01 | 0.16 | 0.02 |
| singlecopter | 8 | 1 | 102 s | 0.13 | 0.13 | 2.93 | 0.06 | 0.07 | 0.09 | 0.68 | 0.04 | 0.07 | 0.03 |
| coaxcopter | 9 | 1 | 102 s | 0.13 | 0.13 | 2.96 | 0.06 | 0.04 | 0.13 | 0.33 | 0.04 | 0.08 | 0.03 |
| Callisto | 4 | 14 | 102 s | 0.12 | 0.12 | 0.73 | 0.05 | 0.17 | 0.26 | 2.25 | 0.06 | 0.06 | 0.02 |
| freestyle | 1 | 1 | 72 s | 0.15 | 0.20 | 0.72 | 0.09 | 0.01 | 0.03 | 0.03 | 0.03 | 0.23 | 0.02 |

Reading these: for the 24 regular layouts (quad, hexa, octa, octa-quad, deca, tri, y6, dodeca-hexa and the three scripted 16- and 32-motor frames) the estimates against the truth are identical to the digit shown (roll 0.13, pitch 0.11, yaw 0.58 degrees, AHRS position 0.06 m; 0.12 to 0.14 for the scripted frames), and so are the altitude and position tracking (0.02 m altitude, 0.16 m north and 0.02 m east). The simulator evidently drives all of them with one common multicopter dynamics model, so the sweep shows that the firmware arms, mixes and flies every layout well enough to complete the mission, not that the aircraft differ. What does differ is the attitude tracking the firmware logs for itself, mostly in yaw: 0.04 degrees for most frames, 0.08 to 0.10 for octa-quad, deca, dodeca-hexa and the 16-motor frames, and 0.35 for the tri-copter, whose yaw is made with a tail servo. The odd models are singlecopter and coaxcopter (classes 8 and 9), where the yaw estimate is worse (2.9 degrees rms against 0.58) and yaw tracking is 0.68 and 0.33 degrees; Callisto, with a yaw tracking error of 2.25 degrees and roll and pitch 0.17 and 0.26; and freestyle, which flew the mission in 69.7 s with a 0.23 m north position error. The motor mixing differs per frame and shows in the logged motor outputs (`RCOU`), which were not compared here. One flight each, simulator only, with the simulator's sensor models and the firmware's own targets. The raw logs (28, about 25 MB gzipped each) are not committed; their checksums are in `raw-log-manifest.txt`.

## What each aerial autopilot sends and accepts over MAVLink

### Message census (no stream request)

`research-tools/sitl-mavlink-census.py`: a fresh simulator per vehicle, no `REQUEST_DATA_STREAM` and no ground-station heartbeat sent, messages counted by name for 60 s on the ground and 30 s during a mission flight (`sitl-evidence/mavlink-census/mavlink-census.csv`).

| Vehicle | Message types | Ground (combined Hz) | Flight (combined Hz) |
|---|---|---|---|
| Copter | 7 | 2.0 | 2.9 |
| Helicopter | 7 | 2.0 | 3.0 |
| Plane | 38 | 52.8 | 74.6 |
| QuadPlane | 38 | 55.8 | 73.3 |

Copter and the helicopter build send only `HEARTBEAT`, `HOME_POSITION`, `GPS_GLOBAL_ORIGIN`, `TIMESYNC`, `PARAM_VALUE`, `MISSION_ITEM_REACHED` and `STATUSTEXT` on a bare connection; a ground station has to request every other stream from them. Plane and QuadPlane send attitude, position, GPS, battery, airspeed, RC channels, EKF status, vibration, wind and more without being asked. The firmware source (`libraries/GCS_MAVLink/GCS_MAVLink_Parameters.cpp`) sets the compiled-in default stream rate to 1 Hz per group for `APM_BUILD_ArduPlane` and 0 for `APM_BUILD_COPTER_OR_HELI`, which matches what was measured and shows this is deliberate firmware behaviour, not a quirk of the simulator. The measured rates (about 1.7 Hz on the ground, 2.3 Hz in flight) are higher than the nominal 1 Hz; why was not investigated.

### Command sweep: every MAV_CMD, zero parameters

`research-tools/sitl-mavlink-command-sweep.py`: every `MAV_CMD_*` named in a `case` label of `GCS_Common.cpp` and the vehicle's own `GCS_MAVLink_*.cpp`, sent as `COMMAND_LONG` and `COMMAND_INT` with every parameter zero, to a disarmed vehicle; the acknowledgement and vehicle text kept. 87 commands for Copter and the helicopter, 88 for Plane and QuadPlane (`sitl-evidence/mavlink-command-sweep-final/command-sweep.csv`):

| Vehicle | ACCEPTED | FAILED | DENIED | UNSUPPORTED | COMMAND_INT_ONLY |
|---|---|---|---|---|---|
| Copter | 40 | 21 | 10 | 5 | 4 |
| Helicopter | 39 | 22 | 10 | 5 | 4 |
| Plane | 34 | 28 | 9 | 6 | 3 |
| QuadPlane | 35 | 27 | 9 | 6 | 3 |

Differences: `MAV_CMD_DO_MOTOR_TEST` is accepted on Copter and QuadPlane but failed on Plane and the helicopter build (consistent with the heli motor-test refusal found earlier); `MAV_CMD_DO_SPRAYER` and `MAV_CMD_DO_CHANGE_SPEED` differ between Copter and Plane; `MAV_CMD_NAV_VTOL_TAKEOFF` is `COMMAND_INT_ONLY` on Copter and the helicopter build but `UNSUPPORTED` on both Plane and QuadPlane (with `Q_ENABLE` set, so VTOL takeoff on a QuadPlane evidently needs the mission-item form, not a direct command, which was not tested here).

**A hang found along the way.** `MAV_CMD_DO_CHANGE_ALTITUDE` (186) sent with all parameters zero is never acknowledged on ArduPlane or QuadPlane, and it stops the MAVLink command channel acknowledging *anything* sent after it on the same connection; four earlier sweep attempts lost the rest of that vehicle's results to this (kept as `sitl-evidence/mavlink-command-sweep`, `-rerun`, `-with-defaults`, `-retry`). The process itself does not crash while this is happening — it keeps answering `HEARTBEAT` and stays alive for at least 120 s with no further commands sent (`sitl-evidence/isolate-replay-crash/`) — but when the hung process is finally killed (`SIGTERM`) it panics: `PANIC: Should not be called on invalid location: Location cannot be (0, 0, 0)`, in `Location::get_alt_cm` (`libraries/AP_Common/Location.cpp:152`), a check compiled in for SITL builds only. This was isolated entirely from the MAVLink interface, without a debugger: an idle run with no commands sent for 180 s never panics (`sitl-evidence/isolate-idle-crash/`); sending `MAV_CMD_DO_CHANGE_ALTITUDE` alone gets no acknowledgement while `MAV_CMD_DO_CHANGE_SPEED` alone is answered normally (`sitl-evidence/isolate-change-altitude-crash/`); replaying the sweep's first 16 commands shows the channel stops answering exactly at that command, and the panic only appears in the log after the final kill, not during the 120 s of idle waiting that followed (`sitl-evidence/isolate-replay-crash/`). The final sweep lists the command as "NOT SENT" with this explanation and so has genuine answers for every other command.

**Resolved from source**, without a debugger: `ArduPlane/GCS_MAVLink_Plane.cpp:handle_command_int_DO_CHANGE_ALTITUDE` always constructs `Location{lat=0, lng=0, int32_t(alt*100), alt_frame}` and calls `get_alt_cm()` on it (through `handle_change_alt_request` -> `Location::get_alt_m`) — the command is deliberately altitude-only, so it never sets a horizontal position, lat/lng stay 0 whatever altitude is requested. With the request altitude also 0 (as the all-zero sweep sends), that Location is the literal `(0, 0, 0)` the SITL-only check in `get_alt_cm` rejects; with any other altitude it is `(0, 0, non-zero)`, which passes. `research-tools/sitl-confirm-change-altitude-nonzero.py` confirms this directly: `DO_CHANGE_ALTITUDE` with altitude 50 m, both `COMMAND_LONG` and `COMMAND_INT`, is `ACCEPTED` immediately, the simulator exits cleanly afterwards, and a follow-up command on the same link still gets answered; the altitude-0 case, repeated in the same run for a direct comparison, reproduces the hang and the panic once more. So the command is not broken in general: an explicit request for **altitude exactly 0** is what triggers it, in both message forms, and that is plausibly a real edge case a ground station or a script could send by mistake (asking to change altitude to sea level, or leaving a parameter at its default 0). `Aerial-Mode-and-Arming-Requirements.md` notes this for anyone building a controlling program against this snapshot.

## GUIDED-mode offboard control: SET_POSITION_TARGET_LOCAL_NED and GLOBAL_INT

`research-tools/sitl-guided-offboard-control.py`: the message pair a companion computer or custom ground station uses for direct control in GUIDED mode, distinct from an uploaded AUTO mission or an immediate `MAV_CMD` (neither tested elsewhere in this repository). Simulator only.

**Copter, `SET_POSITION_TARGET_LOCAL_NED`, position-only** (type_mask bits set to ignore velocity, acceleration and yaw): GUIDED takeoff to 15 m, then one message targeting 20 m north, 10 m east, 20 m altitude (5 m above the takeoff height). After 30 s the vehicle was at exactly 20.0 m north, 10.0 m east, 20.0 m altitude — the target reached precisely, confirmed working as intended.

**Copter, `SET_POSITION_TARGET_LOCAL_NED`, velocity-only**: the same takeoff, then 2.0 m/s north streamed every 0.5 s for 10 s (ArduCopter's GUIDED velocity controller times out without repeated messages, so a one-shot send would not hold). Measured maximum speed 2.01 m/s, matching the command. A single zero-velocity message was then sent and nothing further; 10 s later the vehicle was at -0.02 m/s, essentially stopped. Confirmed working as intended.

**Plane, `SET_POSITION_TARGET_GLOBAL_INT`, position-only, in flight**: an already-flying Plane (AUTO mission, takeoff and two waypoints) was switched to GUIDED and sent one message targeting a point 400 m further along track at 80 m altitude. The vehicle climbed to and held 80 m (the altitude field took effect), but did not fly towards the target: over the next 60 s its position oscillated within a roughly 200 by 300 m box instead of making progress, the straight-line distance to the target going from about 502 m to 527 m.

**Found in source: ArduPlane does not implement the position fields of this message.** `ArduPlane/GCS_MAVLink_Plane.cpp:handle_set_position_target_global_int` decodes the packet, checks only whether altitude is excluded by the type_mask, and if not builds `Location{lat=0, lng=0, alt_cm, frame}` and calls the same `handle_change_alt_request` that `MAV_CMD_DO_CHANGE_ALTITUDE` uses (`ArduPilot-Aerial-Library-Execution-Trace.md`, the MAVLink command-sweep section, above). `pos_target.lat_int` and `pos_target.lon_int` are never read anywhere in the function. So on this snapshot, `SET_POSITION_TARGET_GLOBAL_INT` sent to a Plane in GUIDED can only change altitude; the horizontal position fields are silently accepted and ignored, and GUIDED with no other command just loiters around the point where it was engaged (which is why the aircraft oscillated rather than held still or flew away: a GUIDED loiter, not a fault). A controlling program expecting this message to redirect a Plane's ground target, as it does for Copter, will not get that on this ArduPilot version.

A first Copter attempt (kept, `sitl-evidence/guided-offboard-control-run1-copter-no-position-stream/`) got empty tracks for both parts: Copter does not send `GLOBAL_POSITION_INT` unasked (see the MAVLink census above, 7 message types only), and the script did not request it; fixed with `SET_MESSAGE_INTERVAL`.

**The working alternative: `MAV_CMD_DO_REPOSITION`** (192). Its handler (`handle_command_int_DO_REPOSITION`) does decode the packet's position with `location_from_command_t` and calls `plane.set_guided_WP(requested_position)`, unlike `SET_POSITION_TARGET_GLOBAL_INT` above. Tested on the same flight and the same target: a first attempt (kept, `-run1-no-change-mode-flag`) was refused (`MAV_RESULT_FAILED`) because the aircraft was still in AUTO and the command's `param2` did not carry `MAV_DO_REPOSITION_FLAGS_CHANGE_MODE` (1) — the handler only proceeds when the mode is already GUIDED or that flag is set, and neither was true; that was my test's mistake, not a firmware fault. With the flag set, the command was accepted, the aircraft turned onto and flew to the target, reached the commanded 80 m altitude exactly, and settled into a loiter around the point, 96.0 m from it after 60 s (consistent with ArduPilot's own loiter radius around a reached GUIDED point, not a miss). So on this snapshot, a controlling program should use `MAV_CMD_DO_REPOSITION` with the change-mode flag set, not `SET_POSITION_TARGET_GLOBAL_INT`, to redirect a Plane's horizontal target.

Limits: simulator only; one run per case; only position-only and velocity-only type_masks were tried for the Copter messages, not acceleration terms, yaw, or a mixed mask; `DO_REPOSITION`'s loiter radius and direction parameters were not varied; nothing on a real vehicle.

### The GUIDED-only slew commands: speed, altitude, heading

`AP_PLANE_OFFBOARD_GUIDED_SLEW_ENABLED` adds three commands that only work already in GUIDED mode (`handle_command_int_guided_slew_commands`, `ArduPlane/GCS_MAVLink_Plane.cpp`): `MAV_CMD_GUIDED_CHANGE_SPEED` (43000), `MAV_CMD_GUIDED_CHANGE_ALTITUDE` (43001), `MAV_CMD_GUIDED_CHANGE_HEADING` (43002). The disarmed command sweep above could only show all three failing (not in GUIDED); this run reaches GUIDED with `DO_REPOSITION` first, then flying, sends all three 20 to 21 s apart and holds the last for 40 s.

| Command | Sent | Ack | Observed |
|---|---|---|---|
| `GUIDED_CHANGE_SPEED` | airspeed 30 m/s, accel 2 m/s² | `ACCEPTED` | ground speed rose from about 22 m/s to about 31 m/s within 15 s and stayed there for the rest of the run. Confirmed working. |
| `GUIDED_CHANGE_ALTITUDE` | 120 m, climb rate 3 m/s | `ACCEPTED` | no effect: altitude kept oscillating in the 75 to 81 m band it was already in (around the `DO_REPOSITION` loiter point) for the remaining 60+ s; it never moved toward 120 m. |
| `GUIDED_CHANGE_HEADING` | type 1 (raw heading), 270 degrees | `ACCEPTED` | before this command the heading was sweeping through the full circle every few seconds (14, 340, 96, 190, 291, 16, 102, 187 degrees across the run, the natural effect of circling the `DO_REPOSITION` loiter point); after it, the heading stopped sweeping and held steady at 213 to 215 degrees for the remaining 40+ s — the command clearly did something (it stopped the loiter-driven heading changes) but the steady heading it settled on is not the 270 degrees commanded. |

All three commands returned `ACCEPTED`, but only the speed change matched what was asked for. The altitude change had no visible effect at all despite being accepted; the heading change visibly changed the aircraft's behaviour (it stopped circling and flew a steady course) but not to the commanded value. The altitude discrepancy was followed up. First, the `DO_REPOSITION` waypoint set beforehand was ruled out as the cause: `GUIDED_CHANGE_ALTITUDE` was sent again with GUIDED entered by a plain mode switch (no `DO_REPOSITION`, no waypoint at all, `sitl-evidence/guided-offboard-control/plane-guided-altitude-no-wp-*`) and the altitude still did not climb towards 120 m; it dipped to 72.6 m right after the mode switch and drifted slowly back up to 77.3 m over the next 60 s, nothing like the commanded 3 m/s. `research-tools/sitl-guided-altitude-gdb.py` then put one-shot continuing breakpoints on `ModeGuided::update_target_altitude` (`ArduPlane/mode_guided.cpp`, the function that reads the offboard-slewed target) and `Plane::set_target_altitude_location` (`ArduPlane/altitude.cpp:218`, the only place that applies a new altitude target) over the same scenario: `ModeGuided::update_target_altitude` was hit 650 times and `Plane::set_target_altitude_location` 1417 times, so neither function is being skipped — the mechanism runs. Without a backtrace on each hit (not captured here) this does not show whether `ModeGuided::update_target_altitude`'s own `if` branch (the offboard slew) or its `else` branch (`Mode::update_target_altitude`, the generic per-mode altitude update, also called directly by AUTO before GUIDED was entered, which the 1416 hits recorded for the base-class function separately are more consistent with) is the one producing most of those `set_target_altitude_location` calls. **Not resolved further**: whether the slew branch runs but is immediately overridden by something else, or the branch condition is false and the generic altitude-hold path runs instead.  **Fault injection, added separately:** between the 30 m/s `GUIDED_CHANGE_SPEED` and the altitude command above, a second `GUIDED_CHANGE_SPEED` at -50 m/s (outside `ARSPD_FBW_MIN`/`ARSPD_FBW_MAX`, the envelope `ModeGuided::handle_change_airspeed` checks at `mode_guided.cpp:126`) was sent and refused (ack `MAV_RESULT_FAILED`), with the 30 m/s target still in effect afterwards (final groundspeed ~30.9 m/s) - confirming in a live run what reading the source predicted, rather than asserting it from the source alone.

**The heading discrepancy is resolved: it was my own test's parameter, not a firmware fault.** `ModeGuided::update()` turns the aircraft with a bank angle limited by `target_heading_accel_limit = MAX(packet.param3, 0.05f)` (`ArduPlane/mode_guided.cpp`): my first `GUIDED_CHANGE_HEADING` sent `param3` (the acceleration limit) as 0, which floors to 0.05 m/s², a bank limit of about atan(0.05/9.81) ≈ 0.3 degrees, far too small to turn the aircraft meaningfully in the 40 s window, so it settled near wherever the loiter happened to leave it (213 to 215 degrees, kept as `plane-guided-slew-run1-near-zero-heading-accel-limit`). Resending the same command with `param3` 3.0 m/s² (a normal turn acceleration) reached 269 degrees, within 1 degree of the 270 commanded. One run per case; the three slew commands were tried in one order and spacing only.

## Terrain-relative waypoints (AP_Terrain)

`research-tools/sitl-terrain-following.py`: real elevation data for this project's home location exists in the pinned snapshot's own tree (`terrain/S36E149.DAT`, 2.1 MB; `terrain/S36E148.DAT` is present but empty and not needed here), copied into the simulator's own `terrain/` folder. `TERRAIN_ENABLE` is an enable-flag parameter (a reboot needed, the same two-stage pattern as `SERVO_DSHOT_ESC`/`SOAR_ENABLE`/`AROT_ENABLE`/`BATT_MONITOR` elsewhere in this repository). A Plane mission flew the same route ArduPilot's own `ArduPlane_Tests/TerrainMission/ap-terrain.txt` uses: a takeoff, two `MAV_FRAME_GLOBAL_TERRAIN_ALT` waypoints about 5 km and 3 km from home commanding 100 m above the terrain, and a landing. Completed: both waypoints reached (223 s and 406 s after takeoff), landed and disarmed by itself at 528 s.

The route genuinely changes elevation: the simulated terrain under the aircraft rose from 583 m to 787 m AMSL and back down to about 616 m by the time of the second waypoint (over 200 m of relief along a roughly 8 km round trip). Over that same stretch, the aircraft's height above home swung from 82 m to 298 m, following the rising ground, while its height above the terrain (`TERRAIN_REPORT.current_height`) stayed in a much tighter band: 82.0 to 126.5 m, mean 97.4 m, against the 100 m commanded — a real confirmation that the navigation target was height above ground, not height above home or sea level. The widest excursions (up to 126.5 m) line up with the steepest parts of the climb in terrain, where the aircraft's climb rate could not keep up instantly with the rising ground; the terrain-following control itself was not tuned or judged beyond this.

**Copter, closer waypoints (attempt 2).** The same elevation profile, interpolated to about 580 m and 400 m from home instead of 5 and 3 km, so the flight finishes in a bounded time at Copter speed, commanding 40 m above the terrain. Completed: both waypoints reached (74.7 s and 131.0 s after the mission started), RTL, landed and disarmed at 196.7 s. The real terrain AMSL under the route still changes by 13.1 m over this much shorter distance (583.2 to 596.3 m). The Copter's height above home rose during the climb-out and then fluctuated with the terrain (51.5 m at the high point, down to 39.3 m as the ground fell away), while its height above the terrain converged to the commanded 40 m during the climb and then stayed essentially pegged there for the rest of the cruise (39.9 to 40.3 m, mean 37.3 m including the climb-out) — an even tighter hold than the Plane's, consistent with a multicopter's better vertical control authority at low speed. Two failed Copter attempts are kept: a first with no stream request at all (`sitl-evidence/terrain-following-run1-copter-no-stream-request/`, Copter does not send `TERRAIN_REPORT` or `GLOBAL_POSITION_INT` unasked, the same as the earlier MAVLink census found) and a second (`-run2-copter-stream-request-not-resent-after-reboot/`) where the stream request was sent only before the `TERRAIN_ENABLE` reboot and so had no effect after it — a runtime stream-interval setting does not survive a restart, the same lesson as the parameter-reboot pattern elsewhere in this repository, just for a different kind of setting. 

Limits: simulator only; one flight per vehicle; the terrain data is the project's pinned snapshot's own cached tile, not independently verified against a real elevation source; no terrain data gaps, holes or SRTM voids were tested; the Copter route's 13 m of relief is much smaller than the Plane route's 200+ m.
