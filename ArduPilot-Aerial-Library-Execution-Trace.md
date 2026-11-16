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

**Deferred, not reachable here.** These have no function symbols in either simulator binary: `AP_WindVane`, `AP_DDS` (needs the DDS build option; actually tried, see below), `AP_Module`, `AP_Menu`, `AP_CheckFirmware`, `AP_Devo_Telem`, `AP_ADC`, `AP_DAC`, `AP_IOMCU`, `AP_FlashIface`; and the `AP_HAL_ESP32`, `AP_HAL_QURT`, `AP_HAL_Empty` hardware layers, `AP_ONVIF`, and the `doc` directory are other board builds, a camera protocol or documentation. They stay at level 0, to be examined with a matching board build or hardware. This is a statement about this simulator build only: it does not show the libraries are unused.

**AP_DDS actually tried, unlike the others in that list.** `--enable-DDS` was configured into an isolated build output directory (`-o build-dds`, so the pinned snapshot's own baseline `build/sitl/` binaries used by every other test here were never touched or rebuilt). Configure failed outright: `Checking for program 'microxrceddsgen' : not found`, exit 1. `microxrceddsgen` is the MicroXRCE-DDS IDL code generator AP_DDS's build depends on; this environment has neither it nor a Java runtime at all (`which java`, `which microxrceddsgen` both empty) - installing a JDK and the generator tool is a real toolchain addition, not a quick flag, and was not attempted. The isolated build directory and the one stray `build/linux` directory waf produced after the failed configure were both removed; the pinned snapshot's own `build/sitl/` tree (all seven vehicle binaries) was confirmed unchanged afterward. This is specifically about this WSL environment's installed tools, not about the firmware source.

Limits: function entry only; one flight per vehicle; default parameters; the first and second sweep attempts and the pkill/parser faults are described in the section above.

## Single motor failure: the thrust-loss detector fired, but too late

A fault not tried anywhere else in this project: `SIM_ENGINE_FAIL` (SITL's own motor-kill simulation; `SIM_ENGINE_MUL` defaults to 0, full thrust loss on that motor), on a quad hovering at 30 m in GUIDED. `research-tools/sitl-copter-motor-failure.py` (output `sitl-evidence/copter-motor-failure/`) armed, took off, held 25 s, then killed motor 1.

The quad fell in a smooth, near-continuous near-freefall descent (0 to 14 m/s over about 2.9 s, steadily accelerating, not a controlled or compensated descent) and hit the ground at 14.03 m/s 3.2 s after the motor died. ArduCopter's own detector for exactly this (`Copter::thrust_loss_check`, `ArduCopter/crash_check.cpp`, a 1 s confirmation window on descent-at-high-throttle) did work correctly - `"Potential Thrust Loss (1)"` correctly named motor 1 - but only arrived at t=5.0 s, about 1.8 s *after* the ground-contact text already logged at t=3.2 s. On this frame, at this altitude, the fall itself was faster than the detector's own 1-second trigger window, so by the time it fired the vehicle had already crashed. The vehicle still reported armed for the rest of the 25 s watch; no crash-triggered disarm was seen.

Limits: one run, Copter quad frame only, one starting altitude (30 m) and one hover throttle level; not tried on other frame types, a higher starting altitude (more time for the 1 s window to complete before impact), or a partial thrust loss (SIM_ENGINE_MUL above 0) instead of total loss. A follow-up at 100 m, giving the fall more time before impact, found the opposite problem: the detector never fired at all. The quad fell for 7.8 s before first ground contact (vs 3.2 s from 30 m - longer than the detector own 1 s window) then bounced several more times over the rest of the watch (1.6 to 2.9 m/s impacts), and "Potential Thrust Loss" never appeared once. Most likely reason, from the source already read: thrust_loss_check resets its counter whenever the commanded attitude exceeds 15 degrees (crash_check.cpp) - a guard against false positives during normal manoeuvring, but one that very plausibly suppresses the detector exactly when a quad missing a motor tumbles past 15 degrees trying to correct. Not confirmed with gdb (the counter and commanded-angle values were not traced directly), but it fits both runs: the short 30 m fall caught one lucky contiguous second before things got too far out of level; the much longer 100 m fall gave the vehicle 7x more time to tumble past 15 degrees and never got one. A gdb attempt to confirm this directly (printing the commanded roll/pitch at each `Copter::thrust_loss_check` call) hit the same `copter`-has-unknown-type expression-evaluation wall already documented for `mode_guided.cpp` (the `guided-distance-stall-run5` failed attempt), this time from `crash_check.cpp`; the hypothesis stays unconfirmed by gdb, for the same build-wide reason.
## AP_CheckFirmware: a mislabeled gap, closed essentially for free

The original sweep listed `AP_CheckFirmware` as having no symbols in either simulator binary, but `AP_CHECK_FIRMWARE_ENABLED` is defined as `AP_OPENDRONEID_ENABLED` (`AP_CheckFirmware.h`) - and `AP_OpenDroneID::update` was already confirmed entered in that very same sweep (1,925 hits on Copter), so the symbol must have been present all along; `nm` confirms it (`check_firmware_print`, a free function, the only symbol this library's build actually produces). Its one call site, inside `AP_Vehicle::setup()`, has no runtime gate at all - and `AP_Vehicle::setup()` was already confirmed to run once per boot when `AP_Vehicle` itself was closed earlier. `research-tools/sitl-checkfirmware-gdb.py` (output `sitl-evidence/checkfirmware/`) just confirmed `check_firmware_print` hit once in a plain boot, as predicted.

Two other board-architecture checks, for completeness, no new SITL run: `AP_Module` needs `HAVE_LIBDL`, which waf only checks for the generic `linux` HAL board class (`Tools/ardupilotwaf/boards.py`), never called for the `sitl` board at all - genuinely a different board build, not a param. `AP_Devo_Telem` has `AP_DEVO_TELEM_ENABLED` hard-defined to 0 with no public waf `--enable` flag anywhere (unlike `AP_DDS`'s `--enable-DDS`) - enabling it would mean patching the library's own feature-gate header, which is a different kind of action than toggling a documented build flag or parameter, and was not done.
## AP_SerialLED (NeoPixel backend): present but never entered, closed the same way as AP_PiccoloCAN

The earlier full-function sweep found `AP_SerialLED`'s functions (`send`, `set_RGB`, `set_num_neopixel*`) present but never entered ("no serial LED configured"). Needed no hardware: `NTF_LED_TYPES` bit 8 (256, NeoPixel, OR'd into the existing default) plus `SERVO9_FUNCTION` 120 (`k_LED_neopixel1`) on a Copter boot - the LED driver list is built once at `AP_Notify::init()`, so this needed the usual two-stage reboot (`research-tools/sitl-neopixel-gdb.py`, output `sitl-evidence/neopixel/`). `NeoPixel::NeoPixel` and `SerialLED::init` each hit once; `SerialLED::hw_set_rgb` (the shared base-class send path) hit 192 times in 30 s (~6.4 Hz) - the WS2812 protocol bit-banged out to a servo channel nobody reads, the same spirit as `AP_PiccoloCAN` writing CAN frames nobody answers.

Limits: entry and call-count only, one boot, simulator only, Copter only, NeoPixel backend only - ProfiLED, DShot-LED and the I2C-based serial-LED backends were not tried.
## GUIDED velocity command-loss timeout: confirmed, not just asserted

`copter_velocity()` (`sitl-guided-offboard-control.py`) previously sent an explicit zero-velocity message to stop the stream, which never tested the thing its own docstring already claimed ("ArduCopter's GUIDED velocity controller times out without repeated messages") - a vehicle told to stop stopping is not a fault test. Kept as `sitl-evidence/guided-offboard-control-run1-copter-velocity-explicit-stop-sent/`.

Changed to send nothing at all after the last streamed 2 m/s command, relying purely on `ModeGuided::get_timeout_ms` (`mode_guided.cpp`: "set velocity to zero ... if no updates received for 3 seconds"). Confirmed: ten seconds after the last velocity message, with none sent since, `vx` had fallen to -0.01 m/s. The documented self-timeout genuinely works.
## The horizontal stall, resolved: a terrain-relative speed throttle, not a generic limit

Five gdb attempts at printing `AC_PosControl`'s internal target/current-position values, to see the numbers directly instead of inferring from terrain height, all failed on C++ expression-evaluation quirks specific to this build: `AP_HAL::millis()` and plain `millis()` were both unresolvable from a breakpoint in `mode_guided.cpp`; `pos_control` and then `this->pos_control` were unresolvable at the exact address gdb stopped at; `copter` (the global vehicle singleton) came back with "unknown type" from that translation unit. Kept as five small failed runs (`sitl-evidence/guided-distance-stall-run1`-`run5`).

Dropping gdb and logging `GLOBAL_POSITION_INT` directly instead settled it (`research-tools/sitl-guided-distance-stall.py`, output `sitl-evidence/guided-distance-stall/`): the same far GUIDED position target, but in `MAV_FRAME_GLOBAL_RELATIVE_ALT` instead of terrain-relative, had the vehicle cruise a dead-steady 10 m/s west for the whole 220 s test - 17.6 km covered, zero sign of slowing. The horizontal stall only happens with a terrain-relative target.

`AC_PosControl::input_pos_NED_m`/`terrain_scaler_D_m` explain why: when `terrain_margin_m` is non-zero (true only for a terrain-relative target), the allowed horizontal speed gets multiplied by a scalar that drops toward a hard 0.01 floor as the vehicle's vertical position error grows - a genuine safety feature (don't fly fast horizontally while badly off your intended height above the ground below you), not a bug. That matches the earlier terrain-relative test's slowdown after about 2.4 km far better than a hard stop would: it was most likely crawling at roughly 1% of normal speed, not frozen solid. Not independently confirmed with a working gdb trace of the scalar's actual value - the gdb tooling problems above blocked that - but a working non-terrain control plus the source mechanism both point the same way.
## The horizontal stall: three more causes ruled out by reading, one left standing

Three more hypotheses for why GUIDED's position target stopped advancing, checked against the source and the existing logs with no new SITL run:

1. `ModeGuided::pos_control_run`'s own update-timeout check (`mode_guided.cpp`: "stop rotating if no updates received within `timeout_ms`") only resets yaw to `HOLD` - `guided_pos_target_ned_m` itself is fed to `pos_control->input_pos_NED_m(...)` every loop regardless, unchanged from the original far target. A one-shot position command does not go stale the way the documented GUIDED velocity controller does.
2. `ModeGuided`'s optional travel limit (`guided_limit.horiz_max_m`) defaults to 0.0 (no limit) and is only ever set by an `AUTO` mission's `MAV_CMD_DO_GUIDED_LIMITS` item, which this GUIDED-only test never sent.
3. The existing `sitl-terrain-failsafe-midflight.py` log shows no GCS-failsafe text and only one mode line for the whole 600 s run (`mode GUIDED`, never changing) - ruling out a GCS-link-loss failsafe, worth checking specifically since that script never threads periodic heartbeats the way `run_quadplane_failsafes.py` does.

Leading remaining hypothesis, not yet confirmed with gdb: a clamp or S-curve distance/speed limit inside `AC_PosControl`'s own horizontal (NE) controller. Not pursued further here.
## QuadPlane main-motor failure during cruise: no crash, but a struggling landing approach

A third data point, as an eighth `run_quadplane_failsafes.py` scenario (`motor-failure-cruise`): the main forward/cruise motor (`SERVO3`, `k_throttle`=70, bit 2, value 4) killed during level cruise flight rather than a VTOL lift motor, output in `sitl-evidence/quadplane-failsafes/quadplane-motor-failure-cruise*`.

Unlike losing a VTOL lift motor (which crashed the aircraft in 2.5 s, see above), losing the cruise motor caused no crash at all: the aircraft still reached the final waypoint 1.9 s after the fault, still gliding on its wings with airspeed and lift intact, and entered the mission's `VTOLLand` item normally. The landing approach itself then struggled - `"VTOL Overshoot"` at t=35.4 s, 4.4 s after the fault, with a 66.4 degree yaw error - most likely because managing approach speed and energy during a VTOL landing still relies on some forward thrust that this aircraft no longer had. No ground-contact text appeared and the mode stayed `AUTO`, armed, for the rest of the 90 s watch, which ended before touchdown, so whether it recovered from the overshoot or eventually crashed landing was not observed.

Limits: one run, simulator only, the watch window ended before the outcome of the landing attempt was settled.

**Resolved with a longer watch.** 90 s was not enough; rerun with 150 s (the truncated run kept as `sitl-evidence/quadplane-failsafes-run1-motor-failure-cruise-90s-watch-too-short/`). The aircraft recovered from the overshoot on its own, restarting the approach (`"VTOL position2 started"`) at t=97.9 s - about 62 s after the overshoot - then ran a normal landing sequence (`"Land descend started"` t=101.3, `"Land final started"` t=133.1) and touched down softly at 0.50 m/s at t=144.4 s. It was still reported armed 5.6 s after touchdown when the watch ended, so auto-disarm itself was not confirmed, but the landing succeeded: losing the cruise motor cost a long, ugly approach, not the aircraft.
## QuadPlane VTOL motor failure: no observable effect, unlike the pure Copter case

A direct comparison to the pure-Copter motor-failure test above: the identical `SIM_ENGINE_FAIL=1` fault (one VTOL lift motor killed outright, `SIM_ENGINE_MUL` defaults to 0) added as a new `motor-failure-vtol` scenario to `run_quadplane_failsafes.py` (output `sitl-evidence/quadplane-failsafes/quadplane-motor-failure-vtol*`), injected 6 s into the VTOL takeoff of the same mission the other QuadPlane failsafe scenarios use (VTOL takeoff, two waypoints, VTOL landing).

Unlike the pure Copter, which hit the ground in 3.2 s from a 30 m hover, the QuadPlane showed no observable ill effect at all: the forward transition started at t=13.4 s at airspeed 0.6, the same point the *unfaulted* baseline quadplane flight reaches it (`Plane-Frame-Types-Trace.md`/`sitl-plane-gaps.py`); both waypoints were reached; the return transition and VTOL landing approach proceeded normally through `VTOL position1`/`position2` into `Land descend started` at t=64.5 s; mode stayed `AUTO` and armed stayed true for the whole 91 s watch (which ended before touchdown, so landing completion and disarm were not themselves confirmed).

Most likely explanation, not investigated further: the VTOL takeoff phase here only has to sustain flight for about 13 s before the transition hands lift over to the wings, unlike the Copter test's indefinite sustained hover, so losing 25% of lift capacity for a brief climb-and-transition is tolerable in a way it is not for sustained hover. The VTOL landing descent later in the same flight showed no trouble either, which fits that explanation less well and was not dug into further.

**Correction: that result was the wrong channel.** `SIM_ENGINE_FAIL` is a bitmask of raw SERVO *output channel* numbers (`AP_HAL_SITL/SITL_State.cpp`), not a frame-relative motor index - and reading `SERVO1..8_FUNCTION` from a live quadplane boot showed `SERVO1_FUNCTION` is `k_aileron` (4), not a motor at all; the four VTOL lift motors are on `SERVO5..8` (`k_motor1..4`, 33-36). The run above, using bit 0 (value 1), killed the aileron, not a motor - which fully explains the "no observable effect" result, since losing aileron authority naturally has little impact on hover or a landing approach. That run is kept (`sitl-evidence/quadplane-failsafes-run1-motor-failure-vtol-wrong-channel-aileron/`).

Rerun with the correct bit (16 = bit 4 = `SERVO5` = `k_motor1`, a real VTOL lift motor): the QuadPlane crashed this time too, hitting the ground at 11.50 m/s 2.5 s after the fault. ArduPlane's own `"Potential VTOL Thrust Loss (1)"` message arrived at t=10.6 s - 2.1 s *after* the ground-contact text, the same too-late-detector pattern already found on the pure Copter. The QuadPlane is not meaningfully more resilient to a lost VTOL motor than a pure Copter; the original comparison above and its explanation (brief VTOL phase vs. sustained hover) are both superseded by this corrected run.
## The terrain-failsafe stall: ruled out as a terrain-data problem, cause otherwise still open

Follow-up on the previous section's stall. `research-tools/sitl-terrain-stall-gdb.py` repeated the same 200+ s GUIDED flight toward the empty tile, gdb-counting `ModeGuided::pos_control_run` (the per-loop GUIDED position-controller function; a first attempt watched `AC_WPNav::advance_wp_target_along_track` instead and got zero hits - a single ad-hoc GUIDED position target never uses AC_WPNav's multi-leg path advancer at all, only AUTO-style waypoint sequences do; kept as `sitl-evidence/terrain-stall-run1-wrong-function-no-hits/`), `AC_WPNav::get_terrain_D_m`, the `get_terrain_U_m` it wraps, and `Copter::failsafe_terrain_on_event`.

Result: `pos_control_run` and `get_terrain_D_m` both ran 100,007 times (every loop, unconditionally); `get_terrain_U_m` showed 0 hits despite being `get_terrain_D_m`'s very first statement, almost certainly inlined (the same pattern seen with `_fdm_input_step`, `one_Hz_update` and the CRSF decode functions earlier); `failsafe_terrain_on_event` never fired once. So the vehicle's own current-position terrain data stayed healthy for the whole stall - the failsafe's trigger condition never went false, which is exactly why it never fired.

This rules out a terrain-data explanation for the stall: the vehicle never got anywhere near the 19 km-away tile boundary, stopping only a couple of kilometres out. Why `ModeGuided`'s GUIDED position target stops advancing that early is a separate, still-open question this project did not pursue further. (A second attempt at this same check tried a gdb `dprintf` on specific source lines instead of function names and failed outright, 'No symbol table is loaded' - `dprintf file:line` needs the location resolved before `run` in a way plain function-name breakpoints do not; kept as `sitl-evidence/terrain-stall-run2-dprintf-no-symbol-table/`.) Limits: one run, Copter only, GUIDED mode only, simulator only.
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
## AP_PiccoloCAN: the last "present but never entered" library, closed the same way as AP_RCTelemetry

The original breakpoint sweep found two libraries present in the Copter/Plane binaries but never entered: `AP_PiccoloCAN` and `AP_RCTelemetry`. `AP_RCTelemetry`'s CRSF backend was resolved earlier (its own section above) using ArduPilot's built-in SITL CRSF device. `AP_PiccoloCAN` needed no device at all, just the right CAN configuration: SITL's own CAN simulation defaults to a UDP-multicast transport (`SIM_CAN_TYPE1`, no vcan/SocketCAN or root privilege needed - confirmed this build has neither available, `sudo` here asks for a password). `research-tools/sitl-piccolocan-gdb.py` (output `sitl-evidence/piccolocan/`) set `CAN_P1_DRIVER` 1 and `CAN_D1_PROTOCOL` 4 (PiccoloCAN, both `RebootRequired`, the same two-stage boot used throughout this project) on a Copter boot, then gdb-confirmed `AP_PiccoloCAN::init` and `::update`: 1 and 11,763 hits over about 30 s, both parameters read back correctly after the reboot.

Limits: entry and call-count only, one boot, simulator only; no simulated PiccoloCAN ESC or servo actually answers on the multicast bus, so this confirms the driver's own scheduling, not protocol traffic or an ESC response.
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

All three commands returned `ACCEPTED`, but only the speed change matched what was asked for. The altitude change had no visible effect at all despite being accepted; the heading change visibly changed the aircraft's behaviour (it stopped circling and flew a steady course) but not to the commanded value. The altitude discrepancy was followed up. First, the `DO_REPOSITION` waypoint set beforehand was ruled out as the cause: `GUIDED_CHANGE_ALTITUDE` was sent again with GUIDED entered by a plain mode switch (no `DO_REPOSITION`, no waypoint at all, `sitl-evidence/guided-offboard-control/plane-guided-altitude-no-wp-*`) and the altitude still did not climb towards 120 m; it dipped to 72.6 m right after the mode switch and drifted slowly back up to 77.3 m over the next 60 s, nothing like the commanded 3 m/s. `research-tools/sitl-guided-altitude-gdb.py` then put one-shot continuing breakpoints on `ModeGuided::update_target_altitude` (`ArduPlane/mode_guided.cpp`, the function that reads the offboard-slewed target) and `Plane::set_target_altitude_location` (`ArduPlane/altitude.cpp:218`, the only place that applies a new altitude target) over the same scenario: `ModeGuided::update_target_altitude` was hit 650 times and `Plane::set_target_altitude_location` 1417 times, so neither function is being skipped — the mechanism runs. Without a backtrace on each hit (not captured here) this does not show whether `ModeGuided::update_target_altitude`'s own `if` branch (the offboard slew) or its `else` branch (`Mode::update_target_altitude`, the generic per-mode altitude update, also called directly by AUTO before GUIDED was entered, which the 1416 hits recorded for the base-class function separately are more consistent with) is the one producing most of those `set_target_altitude_location` calls. **Resolved, partially, with a gdb dprintf instead of a backtrace.** `research-tools/sitl-guided-altitude-values.py` printed `Plane::set_target_altitude_location`'s actual `target_altitude.amsl_cm`/`loc.alt` on every call for the no-waypoint scenario above, but used a hardcoded `MAV_FRAME` value of 4 for its own `GUIDED_CHANGE_ALTITUDE` - that is `MAV_FRAME_LOCAL_ENU`, not `MAV_FRAME_GLOBAL_RELATIVE_ALT` (3) - so the command came back `MAV_RESULT_DENIED`, and the climb-then-drop it recorded in that run came from something else entirely, not the slew (kept as a separate, instructive mistake, `sitl-evidence/guided-altitude-values/`).

`research-tools/sitl-guided-altitude-values2.py` reran `plane_guided_slew()`'s own scenario exactly (`DO_REPOSITION` into GUIDED at 80 m, then the correct frame=3) with the same dprintf (`sitl-evidence/guided-altitude-values2/`). `GUIDED_CHANGE_ALTITUDE` was accepted as before, and this time `loc.alt` rose smoothly a few centimetres per 100 ms tick rather than jumping once - a pattern only the rate-based slew code produces, not the generic `Mode::update_target_altitude` fallback - confirming the slew branch really does run. But the slew computes each tick's sub-target from the aircraft's *current* altitude (`plane.current_loc.get_alt_cm`), not from the previous sub-target, so it only advances as fast as the aircraft's real altitude changes between ticks. Over the full 60 s hold it dipped from 75.8 m to a low of 74.0 m and drifted back up to only 77.9 m - essentially flat, nowhere near the commanded 120 m at 3 m/s - most likely because the aircraft's actual altitude was still being held near the earlier `DO_REPOSITION` target by a separate path that this test did not trace with a backtrace, so which other caller is winning the tug-of-war remains open.  **Fault injection, added separately:** between the 30 m/s `GUIDED_CHANGE_SPEED` and the altitude command above, a second `GUIDED_CHANGE_SPEED` at -50 m/s (outside `ARSPD_FBW_MIN`/`ARSPD_FBW_MAX`, the envelope `ModeGuided::handle_change_airspeed` checks at `mode_guided.cpp:126`) was sent and refused (ack `MAV_RESULT_FAILED`), with the 30 m/s target still in effect afterwards (final groundspeed ~30.9 m/s) - confirming in a live run what reading the source predicted, rather than asserting it from the source alone.

**The heading discrepancy is resolved: it was my own test's parameter, not a firmware fault.** `ModeGuided::update()` turns the aircraft with a bank angle limited by `target_heading_accel_limit = MAX(packet.param3, 0.05f)` (`ArduPlane/mode_guided.cpp`): my first `GUIDED_CHANGE_HEADING` sent `param3` (the acceleration limit) as 0, which floors to 0.05 m/s², a bank limit of about atan(0.05/9.81) ≈ 0.3 degrees, far too small to turn the aircraft meaningfully in the 40 s window, so it settled near wherever the loiter happened to leave it (213 to 215 degrees, kept as `plane-guided-slew-run1-near-zero-heading-accel-limit`). Resending the same command with `param3` 3.0 m/s² (a normal turn acceleration) reached 269 degrees, within 1 degree of the 270 commanded. One run per case; the three slew commands were tried in one order and spacing only.

## Terrain-relative waypoints (AP_Terrain)

`research-tools/sitl-terrain-following.py`: real elevation data for this project's home location exists in the pinned snapshot's own tree (`terrain/S36E149.DAT`, 2.1 MB; `terrain/S36E148.DAT` is present but empty and not needed here), copied into the simulator's own `terrain/` folder. `TERRAIN_ENABLE` is an enable-flag parameter (a reboot needed, the same two-stage pattern as `SERVO_DSHOT_ESC`/`SOAR_ENABLE`/`AROT_ENABLE`/`BATT_MONITOR` elsewhere in this repository). A Plane mission flew the same route ArduPilot's own `ArduPlane_Tests/TerrainMission/ap-terrain.txt` uses: a takeoff, two `MAV_FRAME_GLOBAL_TERRAIN_ALT` waypoints about 5 km and 3 km from home commanding 100 m above the terrain, and a landing. Completed: both waypoints reached (223 s and 406 s after takeoff), landed and disarmed by itself at 528 s.

The route genuinely changes elevation: the simulated terrain under the aircraft rose from 583 m to 787 m AMSL and back down to about 616 m by the time of the second waypoint (over 200 m of relief along a roughly 8 km round trip). Over that same stretch, the aircraft's height above home swung from 82 m to 298 m, following the rising ground, while its height above the terrain (`TERRAIN_REPORT.current_height`) stayed in a much tighter band: 82.0 to 126.5 m, mean 97.4 m, against the 100 m commanded — a real confirmation that the navigation target was height above ground, not height above home or sea level. The widest excursions (up to 126.5 m) line up with the steepest parts of the climb in terrain, where the aircraft's climb rate could not keep up instantly with the rising ground; the terrain-following control itself was not tuned or judged beyond this.

**Copter, closer waypoints (attempt 2).** The same elevation profile, interpolated to about 580 m and 400 m from home instead of 5 and 3 km, so the flight finishes in a bounded time at Copter speed, commanding 40 m above the terrain. Completed: both waypoints reached (74.7 s and 131.0 s after the mission started), RTL, landed and disarmed at 196.7 s. The real terrain AMSL under the route still changes by 13.1 m over this much shorter distance (583.2 to 596.3 m). The Copter's height above home rose during the climb-out and then fluctuated with the terrain (51.5 m at the high point, down to 39.3 m as the ground fell away), while its height above the terrain converged to the commanded 40 m during the climb and then stayed essentially pegged there for the rest of the cruise (39.9 to 40.3 m, mean 37.3 m including the climb-out) — an even tighter hold than the Plane's, consistent with a multicopter's better vertical control authority at low speed. Two failed Copter attempts are kept: a first with no stream request at all (`sitl-evidence/terrain-following-run1-copter-no-stream-request/`, Copter does not send `TERRAIN_REPORT` or `GLOBAL_POSITION_INT` unasked, the same as the earlier MAVLink census found) and a second (`-run2-copter-stream-request-not-resent-after-reboot/`) where the stream request was sent only before the `TERRAIN_ENABLE` reboot and so had no effect after it — a runtime stream-interval setting does not survive a restart, the same lesson as the parameter-reboot pattern elsewhere in this repository, just for a different kind of setting. 

Limits: simulator only; one flight per vehicle; the terrain data is the project's pinned snapshot's own cached tile, not independently verified against a real elevation source; no terrain data gaps, holes or SRTM voids were tested; the Copter route's 13 m of relief is much smaller than the Plane route's 200+ m.

## AP_InternalError: the "should never happen" detector, confirmed live and quiet

Another ap-lib gap left at L1 (named in a trace, not executed). `AP_InternalError.cpp` is a small bitmask of "this should never happen" flags (`error_t::flow_of_control`, `constraining_nan`, `stack_overflow`, and so on) raised by `INTERNAL_ERROR(...)` call sites scattered across the vehicle code and several core libraries (`AP_Scheduler`, `AP_Math::constrain_value`, `AC_WPNav_OA`, `AC_PosControl`, ArduCopter's `mode_auto.cpp`/`mode_guided.cpp`, ArduPlane's `quadplane.cpp`/`altitude.cpp`, and more) - all of them internal sanity-check guards ("this should never happen because X"), not failures a pilot or GCS could cause directly. `AP_INTERNALERROR_ENABLED` defaults to 1 for every board (`AP_InternalError_config.h`), so the detector itself is always compiled in.

The one consumer that matters operationally is `AP_Arming::system_checks()` (`AP_Arming.cpp`): on every prearm check pass it checks `AP::internalerror().errors() != 0` and, if any bit is set, refuses to arm with `"Internal errors 0x%x l:%u %s"` naming the exact source line (`last_error_line()`) that raised it. `research-tools/sitl-internalerror-gdb.py` (output `sitl-evidence/internalerror-gdb/`) confirmed this directly on a plain Copter boot: `AP_Arming::system_checks` hit 17 times across one connect, arm and disarm cycle - prearm checks clearly run continuously in the background, not only at the moment of an arm request - while `AP_InternalError::error` itself was hit 0 times. The detector is live and reachable, and correctly stayed silent through entirely normal operation with no false positive.

Also tried, and explicitly a dead end: getting a NaN into this path for real, to see the "Internal errors" prearm refusal actually fire. `AP_Math::constrain_value` (one of the `INTERNAL_ERROR(error_t::constraining_nan)` call sites, used extremely widely throughout the codebase) looked like the easiest target via a `PARAM_SET` carrying a NaN value, but `GCS_Param.cpp`'s `handle_param_set()` explicitly checks `isnan(packet.param_value) || isinf(packet.param_value)` and rejects it outright with `MAV_PARAM_ERROR_VALUE_OUT_OF_RANGE` before the value is ever stored - unlike the already-documented NaN mission-upload case elsewhere in this project, which reaches an uncaught exception in `check_lat(float)` by a completely different, less-guarded path. No safe, externally-triggerable way to actually set an internal-error bit was found in this sweep.

Limits: one boot, Copter only, simulator only; the dozens of other `INTERNAL_ERROR` call sites across the vehicle and library code were read but not individually attempted; whether any of them is reachable from outside without an actual firmware bug was not investigated further.

## AP_RAMTRON: wired into SITL's own storage backend, but the flag that should select it does nothing

Another ap-lib gap at L1 (named in a trace, not executed) - but unlike `AP_Module`/`AP_HAL_Linux` (which genuinely need a different board class) or `AP_DDS` (which needs an external codegen tool), `AP_RAMTRON`'s FRAM storage backend looked reachable with no hardware and no different build at all. `AP_HAL_SITL/Storage.h` defines `STORAGE_USE_FRAM` as `HAL_WITH_RAMTRON`, which `Tools/ardupilotwaf/boards.py` defines unconditionally to 1 in the SITL board's own `configure_env()` - not gated behind any other board class. `AP_HAL_SITL/SPIDevice.cpp` even registers a stub `{"ramtron", 0, 0}` SPI device entry so `AP_RAMTRON::init()`'s call to `hal.spi->get_device_ptr("ramtron")` would succeed rather than fail outright. The backend is meant to be selected at runtime with `--set-storage-fram-enabled 1` (`AP_HAL_SITL/SITL_cmdline.cpp`).

Tried it directly: `research-tools/sitl-ramtron-gdb.py` (output `sitl-evidence/ramtron-gdb/`) booted a Copter with that flag under gdb, watching `AP_RAMTRON::init`/`read`/`write`, `HALSITL::Storage::_storage_open` and `AP_HAL::panic`. The boot, an arm and a disarm all completed normally with no panic message and no crash. `HALSITL::Storage::_storage_open` was hit 8974 times (it runs on effectively every storage touch, not just once), but `AP_RAMTRON::init` was never called even once - 0 hits - and decisively, the plain POSIX `eeprom.bin` file was still created in the working directory, which only happens if the function fell through past the FRAM branch to the POSIX one. The flag that should select FRAM storage, per a straightforward reading of the source, did nothing observable on this build.

A follow-up gdb attempt to print `hal.get_storage_fram_enabled()` directly at the `_storage_open` breakpoint, to settle whether the runtime flag or the compile-time macro is the actual blocker, hit the same build-wide expression-evaluation limitation already documented elsewhere in this project (member/singleton access failing with `"Attempt to extract a component of a value that is not a structure"` this time, a new error string for the same underlying wall already seen as `"'copter' has unknown type"` and several `"No symbol ... in current context"` variants) - so the actual reason was not run down further in this sweep. `AP_RAMTRON` stays an open gap, now characterized (compiled in, wired into the SITL board's own config, but its selection flag confirmed inert) rather than simply untried.

Limits: one run, Copter only, simulator only; whether the block is in cmdline-flag parsing, the `hal` flag plumbing, or the `STORAGE_USE_FRAM` macro resolving to 0 in this exact compiled binary despite the source reading 1, was not distinguished.

## ArduPlane deepstall landing (LAND_TYPE=1): dispatch reachable, but the maneuver never got past entry

The standalone `PID` library (`libraries/PID`, distinct from `AC_PID`) was an unresolved ap-lib gap, and its only caller anywhere in the tree is `AP_Landing_Deepstall` - ArduPlane's deepstall landing type (`LAND_TYPE`=1), an intentionally-stalled, full-rudder spiral descent used instead of a normal glide-slope landing. `HAL_LANDING_DEEPSTALL_ENABLED` is `(HAL_PROGRAM_SIZE_LIMIT_KB > 1024)` (`AP_Landing_config.h`), true on SITL, so it should be compiled in. `LAND_TYPE` is an `AP_PARAM_FLAG_ENABLE` parameter, the usual two-stage-reboot pattern used repeatedly elsewhere in this project.

`research-tools/sitl-plane-deepstall-gdb.py` (output `sitl-evidence/deepstall-gdb/`) flew a plain Plane takeoff/two-waypoint/LAND mission with `LAND_TYPE`=1 and a steady 4 m/s crosswind (deepstall needs a wind estimate to plan its approach), watching `AP_Landing_Deepstall::do_land`, `build_approach_path`, `update_steering`, `verify_land`, `override_servos` and `PID::get_pid` with gdb. The vehicle reached the mission's `LAND` item at t=28.6 s - `do_land` hit once, confirming the deepstall type dispatch is genuinely reachable code, not dead code behind the compile flag - but only 14.8 s later, at t=43.4 s, the simulator reported `"SIM Hit ground at 5.504142 m/s"`, and then kept reporting ground contact roughly once a second (mostly 2.3-2.8 m/s bounces, with a few gaps) for the entire remaining ~270 s of the watch window. The aircraft never settled and never disarmed; the test ended with it still bouncing.

`verify_land` ran 2714 times and `override_servos` 13570 times - both plainly run on every loop tick once the LAND item is active, regardless of outcome - but `build_approach_path`, `update_steering` and `PID::get_pid` were never called even once (0 hits each). The actual deepstall-specific work - planning the S-turn approach path and running the steering PID through the stall - was never reached; only the generic landing-type dispatch and its per-tick bookkeeping were. Most likely explanation, not diagnosed further: the mission handed the aircraft straight into the LAND item from a waypoint only 51 m away, with every `DS_*` tuning parameter left at its compiled default, and `verify_land` evidently checks some entry condition (distance, heading relative to wind, or altitude) before calling `build_approach_path` that this approach never satisfied - so the aircraft fell straight into the ground-contact/bounce loop instead of ever flying the actual deepstall S-turn.

This leaves the standalone `PID` library itself still unconfirmed at the code level: its one real caller in the whole tree was shown reachable, but the library's own `get_pid` was not exercised. Limits: one run, Plane only, simulator only; proper deepstall entry geometry (approach distance and heading relative to the commanded wind, non-default `DS_*` tuning) was not attempted, and the repeated-bounce failure mode itself was not investigated beyond what the STATUSTEXT stream already shows.

## Nine more ap-lib gaps closed by source reading alone, no new SITL run

A sweep of the remaining ap-lib gaps that looked, on their face, like they might need real hardware or a different build - checking each one's actual gating in source rather than assuming, the same way `AP_Module`/`AP_Devo_Telem` were closed earlier. None of these needed a new SITL run; all nine are genuinely out of reach of a `sitl`-board run for a documented, specific reason:

- **`AP_HAL_ChibiOS`** and **`AP_HAL_Empty`**: both wrap their entire class implementation (`HAL_ChibiOS_Class.cpp`, `HAL_Empty_Class.cpp`) in a top-level `#if CONFIG_HAL_BOARD == HAL_BOARD_CHIBIOS` / `== HAL_BOARD_EMPTY` guard. This build's `CONFIG_HAL_BOARD` is `HAL_BOARD_SITL` (set unconditionally in the sitl board's own `configure_env()`, `Tools/ardupilotwaf/boards.py`), so both guards are never true and both files compile to empty translation units - mutually exclusive with the sitl board by construction, not a parameter or a missing simulation away from working.
- **`AP_HAL_ESP32`** and **`AP_HAL_QURT`**: built with their own platform-specific toolchains (Espressif's ESP-IDF, Qualcomm's Hexagon SDK respectively), entirely outside the sitl board's waf build graph - the same category as `AP_DDS` needing the external `microxrceddsgen` tool, confirmed earlier this project. Not reachable from a sitl run regardless of any command-line flag or parameter.
- **`AP_IOMCU`**: talks to the separate IO co-processor present on some real FMU boards (its own firmware, running on a second microcontroller). Gated by `HAL_WITH_IO_MCU`, which defaults to 0 (`AP_HAL/AP_HAL_Boards.h`) and is only ever set to 1 inside specific ChibiOS board `hwdef` files; the sitl board's own configuration never touches it, and SITL has no simulated IO MCU at all.
- **`AP_FlashIface`**: a JEDEC SPI/QSPI flash-chip interface whose only callers anywhere in the tree are `Tools/AP_Bootloader/AP_Bootloader.cpp` and `bl_protocol.cpp` - the bootloader is a wholly separate build target from `ArduCopter`/`ArduPlane`/`ArduCopter`'s QuadPlane build, never part of a vehicle firmware build at all.
- **`AP_ADC`** (the ADS1115 external I2C ADC chip driver) and **`AP_DAC`** (TIx3204/MCP40D1x DAC chip drivers): their only callers anywhere in the tree are `AP_HAL_Linux` (a different board class entirely from sitl) and `Tools/AP_Periph` (the CAN peripheral firmware, a separate build target from the main vehicle firmware) - never wired into ArduCopter/ArduPlane/QuadPlane's own sitl build.
- **`libraries/doc`**: not a code library at all. It contains only a `Doxyfile` and an `updateDocs` shell script (documentation-generation tooling) and was only ever picked up as an "ap-lib gap" because this project's own coverage sweep lists every subdirectory of `libraries/` without distinguishing code from tooling. Closed by inspection - there is nothing in it to test.

All nine: source-only confirmation, no new SITL run, no hardware.

## The last eight ap-lib gaps closed, clearing the ap-lib list entirely

The remaining `ap-lib` L1 gaps after the nine closed above. Three were already investigated earlier this project but never given their own claim row; the other five are new, source-only confirmations:

- **`AP_DDS`**: already tried directly (see the `AP_CheckFirmware`/`AP_Module`/`AP_Devo_Telem` section above) - `--enable-DDS` configured into an isolated build output failed outright (`microxrceddsgen` not found; this environment has neither it nor a Java runtime). A genuine toolchain gap, not a flag.
- **`AP_Module`**: needs `HAVE_LIBDL`, checked by waf only for the generic `linux` HAL board class, never for `sitl` - a different board build entirely.
- **`AP_Devo_Telem`**: `AP_DEVO_TELEM_ENABLED` is hard-defined to 0 in its own header with no public waf `--enable` flag at all (unlike `AP_DDS` or `AP_ONVIF` below) - would need patching the library's own feature-gate header, a different kind of action than every other closure in this project.
- **`AP_Menu`** (`libraries/AP_Menu`, a "Simple commandline menu subsystem"): its only two callers anywhere in the tree are `libraries/AP_HAL/examples/RCOutput2/RCOutput.cpp` and `libraries/AP_HAL_Linux/examples/GPIOTest/GPIOTest.cpp` - standalone example programs, separate build targets, never part of any vehicle firmware build.
- **`AP_Radio`** (CC2500/CYRF6936/BK2425 SPI RC-receiver chip drivers, used by ArduCopter's optional `toy_mode` and `AP_RCProtocol`'s radio backend): gated by `AP_RADIO_ENABLED`, default 0 (`AP_Radio_config.h`), with no override anywhere in `Tools/ardupilotwaf/boards.py` - only specific ChibiOS boards with the real chip populated enable it. `toy_mode.cpp`'s own mentions of "cypress radio"/"cc2500 radio" are just comments describing real transmitter button mappings, not reachable code. No simulated SPI radio chip exists in SITL.
- **`AP_ONVIF`** (network camera PTZ control via the ONVIF protocol): its own `wscript` is only recursed into `if bld.env.ENABLE_ONVIF` (the main `wscript`), set solely by `--enable-onvif`, which this project's pinned sitl build was never configured with. Its build also needs an external `gsoap` submodule and the `soapcpp2` stub compiler (`cfg.find_program('soapcpp2')` in `AP_ONVIF/wscript`) - the same category of external-tool dependency as `AP_DDS`'s `microxrceddsgen`, confirmed by reading the build configuration rather than repeating a failed build attempt.
- **`AP_Torqeedo`** and **`AP_WindVane`**: Rover-only (an electric outboard-motor driver with its own battery-monitor backend, and a sailboat wind-vane steering input respectively) - their only callers anywhere in the tree are `Rover/*` and their own backend files. Not a technical gap; simply out of this sweep's aerial (Copter/Plane/QuadPlane) scope while Rover work stays paused by earlier instruction.

All eight: source-only confirmation, no new SITL run, no hardware. This clears the ap-lib gap list entirely (8 -> 0 L1 rows); the ap-lib area is now fully at either L3 or explained-out-of-reach.

## ICE engine: a real RPM-threshold stall-cycling instability, found while trying to fault-inject the RC-failsafe ignition kill

`ledger:plane-ice-engine-start`'s original confirmation (RC11 held at 1900, RC11_OPTION 179) only checked that `"Engine running"` appeared once; it never had a fault injected. `AP_ICEngine::update()` has a documented RC-failsafe interaction worth testing directly: `ICE_OPTIONS` bit 0 (`DISABLE_IGNITION_RC_FAILSAFE`) forces `should_run=false` once `AP_Notify::flags.failsafe_radio` is set, and from `ICE_RUNNING` that logs `"Stopped engine"` (`AP_ICEngine.cpp`).

`research-tools/sitl-plane-ice-failsafe.py` (output `sitl-evidence/plane-ice-failsafe/`) set `ICE_OPTIONS`=1, flew the `plane-ice` airframe into `AUTO` the same way as before, and injected `SIM_RC_FAIL`=1 six seconds after the engine first reported running. The targeted `"Stopped engine"` message never appeared in a 180 s watch - but not because the failsafe path is broken: a different, pre-existing instability swamped the test entirely. The engine cycled `"Engine running"` -> `"Uncommanded engine stop"` -> `"Starting engine"` roughly every 5 seconds for the *entire* 180 s window, both before and after the fault was injected, with no visible difference. `"Uncommanded engine stop"` comes from a different branch than the one this test targeted - `AP_ICEngine.cpp`'s RPM check under `case ICE_RUNNING` (`rpm_instance > 0`, `RPM_THRESH` default 100): the simulated RPM reading kept falling below threshold while the engine was nominally running, which the code treats exactly like an unplanned stall and retries the starter for.

This is a genuinely new finding, separate from what this attempt set out to test: the simulated RPM feedback for this ICE frame never stabilizes above its own threshold, so the engine never actually settles into continuous running at all - not a one-off, but a repeating cycle for the whole flight. Because of that pre-existing cycling, any single engine-stop after the fault could not be attributed to the RC-failsafe ignition kill rather than the RPM-threshold stalls already happening on their own; the specific positive case this test set out to confirm (a `"Stopped engine"` caused by `ICE_OPTIONS` + RC failsafe, not by RPM noise) stays unconfirmed.

Limits: one run, Plane only, simulator only; `starter_time`/`starter_delay`/`RPM_THRESH` tuning that might stabilize the RPM feedback was not attempted; the fault was injected only 6 s into an already-cycling engine, a cleaner test might inject it during one of the brief `"Engine running"` windows rather than racing the cycle.

## Helicopter engine failure: no automatic autorotation, and the same too-late thrust-loss detector

`ledger:heli-flight-and-autorotation`'s existing confirmation only ever entered `AUTOROTATE` by directly requesting the mode - no real engine failure was ever simulated, so whether ArduCopter detects an engine failure automatically on a helicopter and reacts on its own was never actually tested. Reading `ArduCopter/heli.cpp` and `AC_Autorotation.cpp` first: there is no automatic engine-failure detector that switches a heli into `AUTOROTATE` by itself. `heli_update_autorotation()` only reacts to the motor *interlock* switch being off (a pilot action), and `AC_Autorotation.cpp` is purely the head-speed/collective controller used once the vehicle is already in that mode - nothing in either file watches for an unplanned RPM loss and changes mode in response.

Confirmed directly: `research-tools/sitl-heli-engine-failure.py` (output `sitl-evidence/heli-engine-failure/`) flew the heli normally into `AUTO`/loiter using the same launch and interlock recipe as the earlier confirmation, read the live `SERVOx_FUNCTION` values to find the real motor channel (channel 1, `k_motor1`) rather than assuming one, then injected `SIM_ENGINE_FAIL` on that channel without touching the flight mode at all. The helicopter hit the ground at 6.34 m/s 4.7 s later with no automatic mode change and no failsafe text of any kind in between - exactly what the source predicted: nothing automatic intervenes, and a heli that loses its engine in a normal mode simply falls unless the pilot reacts.

`Copter::thrust_loss_check` - the same detector already characterized elsewhere in this project as firing too late for a quad frame (1.8 s after ground contact from 30 m) - did eventually fire (`"Potential Thrust Loss (1)"`), but only 10 s *after* the ground-contact text this time. The too-late pattern extends to the helicopter frame too, and considerably worse here than in the quad case.

Limits: one run, Heli frame only, simulator only; the fault was injected during a loiter, not during takeoff or a maneuver; whether a pilot-reacted autorotation entry (switching the interlock off and selecting `AUTOROTATE` immediately after the failure) would have saved the aircraft was not tested in the same run - that is the existing, separate `AUTOROTATE`-mode confirmation above, never combined with an actual engine failure.

## Precision landing: a target-loss failsafe that actually ran on schedule

`ledger:copter-precision-landing`'s existing confirmation landed cleanly with both simulated backends, but the target was never lost mid-descent. `AC_PrecLand.cpp` documents exactly what should happen if it is: `LANDING_TARGET_TIMEOUT_MS` (2000 ms) before `target_acquired()` goes false and a one-time `"Target Lost"` message is sent, then `PLND_TIMEOUT` (`_retry_timeout_s`, default 4 s) is how long the vehicle keeps descending anyway before deciding whether to retry.

`research-tools/sitl-copter-precland-target-lost.py` (output `sitl-evidence/precland-target-lost/`) reused the SITL-backend (`PLND_TYPE`=4) setup from the earlier confirmation, climbed to 9.2 m in `GUIDED`, switched to `LAND`, and once precision landing was actively tracking the simulated target at 6.0 m height, set `SIM_PLD_ENABLE`=0 - the simulated target simply stops being seen, the same as an occluded beacon in real life. The result matched the source almost exactly:

- t+2.0s: `"PrecLand: Target Lost"` (matches `LANDING_TARGET_TIMEOUT_MS` exactly)
- t+4.0s after that: `"PrecLand: Retrying"` (matches `PLND_TIMEOUT`'s default exactly)
- t+6.2s after retrying started: `"PrecLand: Retry Completed"` then immediately `"PrecLand: Failsafe Measures"` - the climb-and-relook maneuver concluding the target still cannot be found, falling back rather than searching further
- t+19.3s after that: `"SIM Hit ground at 0.50 m/s"` - a normal, soft landing, same speed as every other clean landing in this project
- Disarmed cleanly 2.1 s later, at rest 0.94 m from the original target and 5.05 m from home - essentially the same accuracy as the no-fault confirmation

Unlike several other failsafe and detector investigations elsewhere in this project - the GPS-loss EKF failsafe that never fired even through a hard crash, the quad and helicopter `Copter::thrust_loss_check` detectors that both fired well after ground contact - this one behaved exactly as documented, on the documented schedule, with a genuinely safe outcome.

Limits: one run, Copter only, simulator only; `PLND_STRICT` was left at its default, so a stricter setting's behavior (for example aborting to `RTL` instead of falling back to a normal landing at the current position) was not tried; the target was lost only once, not repeatedly or at a lower height.

## AUTOLAND's automatic trigger: FS_LONG_ACTN 5, never tried, works exactly as documented

The existing `AUTOLAND` confirmation (`ledger:plane-autoland-and-thermal`) only ever entered the mode by direct request. ArduPlane also documents an automatic trigger for it that no scenario anywhere in this project had tried: `FS_LONG_ACTN`=5 - `"will switch to AUTOLAND mode if possible, otherwise RTL mode"` (`ArduPlane/Parameters.cpp`) - fired by the same long-GCS/RC-failsafe mechanism every other `gcs-link-loss`/`rc-loss`/`battery-low` scenario in this project has already exercised, just with action 1 (RTL) instead of 5.

Added a new scenario, `gcs-link-loss-autoland`, to `custom-gcs/integration/run_plane.py`'s `FAILSAFES` dict (`FS_GCS_ENABL`=1, `FS_LONG_ACTN`=5, `FS_LONG_TIMEOUT`=5, heartbeats stopped 15s into an `AUTO` mission), output `sitl-evidence/plane-autoland-failsafe/`. Exactly 5.0s after the heartbeats stopped - matching `FS_LONG_TIMEOUT` precisely - `"GCS Failsafe On: switched to Autoland"` appeared and the mode changed to `AUTOLAND` by itself. The aircraft then flew a complete autoland sequence on its own (`"Loiter to alt complete"`, `"Landing approach start"`, a glide slope, a flare) and landed softly at 0.46 m/s, auto-disarming 2.30 m from the `LAND` point and 2 m from home.

The automatic trigger works exactly as documented, on schedule, with a fully clean outcome - the same pattern as the precision-landing target-loss failsafe elsewhere in this project, and unlike several other failsafes investigated here (the GPS-loss EKF failsafe that never fired, the thrust-loss detectors that fired too late for both quad and heli frames) that did not behave as their own documentation predicted.

Limits: one run, Plane only, simulator only; the fault was injected mid-cruise, not during takeoff or an existing landing sequence; whether `FS_LONG_ACTN`=5 falls back to RTL when AUTOLAND genuinely is not possible (as the parameter description says it should) was not tried.

## FOLLOW mode against a live synthetic target, not just PID numerics

`ledger:swarm-control` had only ever been tested as `AC_PID` numerics in isolation (`Swarm-Trace.md`) - no multi-vehicle SITL, no live `AP_Follow` behaviour. Rather than a second full SITL instance, `research-tools/sitl-copter-follow.py` synthesizes a moving "leader" by sending `GLOBAL_POSITION_INT` from a second MAVLink sysid over the same link, and checks whether a real Copter in `FOLLOW` mode (`FOLL_ENABLE`=1, `FOLL_SYSID` pointed at the synthetic leader, `FOLL_OFS_X/Y/Z`=0) actually moves toward it.

Four earlier attempts in this sweep failed on test-script problems rather than ArduPilot behaviour, in order: no `GLOBAL_POSITION_INT` stream request (nothing was observed at all, matching the earlier MAVLink-census finding that Copter streams nothing by default); no visibility into mode or armed state during the watch loop, which masked a real failure; and an unchecked `GUIDED` mode-set that silently failed - the vehicle stayed in `STABILIZE` with no stick input and auto-disarmed at t=4.2s, which is the actual reason it never moved in that attempt. None of the four is individually preserved (each reused the same output path and overwrote the last) - a process mistake, worth naming plainly rather than glossing over.

With `GUIDED` confirmed active before arming, the fifth attempt worked cleanly: took off, entered `FOLLOW` (`"N-E-D follow offset loaded"`), and genuinely tracked the moving synthetic leader. Distance closed from 15m to 5.7m while the leader was still stationary (the first ~3s), then grew to about 53m as the leader accelerated to 2 m/s, then held essentially constant at 52.7-52.8m for the remaining ~45s of the watch while the vehicle's own position kept moving north in lockstep with the leader's heading and speed.

This confirms `FOLLOW` mode genuinely commands the vehicle toward a live, moving MAVLink target - not just an isolated PID calculation - but the vehicle settled into tracking the leader's *velocity* without closing the position gap that had opened during the climb/transition phase; the roughly 53m steady-state lag was not explained further (plausibly `FOLL_ACCEL_NE`/`FOLL_JERK_NE`'s default limits needing longer than a 60s window to close a gap that size).

Limits: one run, Copter only, simulator only; a synthetic single-sysid leader over the same link, not a second real SITL vehicle; the steady-state lag's cause (controller tuning vs. some other limit) was not investigated; `FOLL_OFS_TYPE`, non-zero offsets and `FOLL_YAW_BEHAVE` were not tried.

## Why the tailsitter reboot is needed, closed by source reading alone

The earlier `copter-tailsitter-reboot` finding confirmed the quadplane-copter_tailsitter frame needs an extra restart to fly ("tailsitter needs extra re-boot to pick up the rotated AHRS view", ArduPilot's own autotest comment) but explicitly left *why* unexamined. Source reading alone closes it, no new SITL run needed:

`Q_TAILSIT_ENABLE` (`Tailsitter::enable`, `ArduPlane/tailsitter.cpp`) is an `AP_PARAM_FLAG_ENABLE` parameter, the same category as every other enable-flag requiring a reboot elsewhere in this project. `QuadPlane::setup()` (`ArduPlane/quadplane.cpp`) builds the rotated attitude reference frame the VTOL controller uses for a tailsitter exactly once per boot:

```cpp
ahrs_view = ahrs.create_view((tailsitter.enable > 0) ? ROTATION_PITCH_90 : ROTATION_NONE, ahrs_trim_pitch);
```

`setup()` runs during the vehicle's boot sequence - well before any GCS client can connect and send a `PARAM_SET`. So on a freshly-wiped first boot, `Q_TAILSIT_ENABLE` is still whatever the `default_params` file set it to (0, unless the model's own `.parm` file pre-configures it) at the exact moment `ahrs_view` is constructed. Setting it live afterward only updates the persisted value in storage - the already-built, wrongly-oriented (`ROTATION_NONE`) `ahrs_view` stays in place for the rest of that boot, regardless. Only the *second* boot (restarted without wiping, so the now-persisted `Q_TAILSIT_ENABLE`=1 loads from storage before `setup()` runs this time) constructs `ahrs_view` with the correct `ROTATION_PITCH_90` - matching exactly why ArduPilot's own `FlyEachFrame` autotest, and this project's earlier confirmation, both needed that extra non-wiping restart to fly the frame at all.

## Proximity-based avoidance holds a simulated boundary, but as an oscillating band, not a clean stop

`AC_Avoid`'s proximity-based avoidance (`AC_AVOID_USE_PROXIMITY_SENSOR`, on by default in `AVOID_ENABLE`'s `AC_AVOID_DEFAULT`) had only ever been confirmed by ArduPilot's own autotest names matching (`ap-lib:AC_Avoidance`), never tested directly. `AP_Proximity_SITL` (`PRX1_TYPE`=10, an `AP_PARAM_FLAG_ENABLE` parameter, the usual two-stage reboot) reports distance to the loaded inclusion-fence polygon boundary as if it were a physical obstacle ring - `AP_Proximity_SITL.cpp` reads `AC_Fence`'s own polyfence directly.

`research-tools/sitl-copter-avoid-proximity.py` (output `sitl-evidence/copter-avoid-proximity/`) uploaded a simple inclusion fence with its north edge 30m from home, set `FENCE_ACTION`=0 (report only, no breach action - specifically to isolate the soft avoidance braking from the fence's own hard breach response), took off, and streamed a continuous `GUIDED` velocity command of 5 m/s due north - straight at and through the fence line - for 45 seconds.

The vehicle accelerated smoothly to about 4.5-5 m/s, then decelerated as it neared the boundary, closest approach 0.42m (noticeably closer than the default 2m `AVOID_MARGIN` would suggest, not explained further) - and never crossed the line. For the remaining ~37 seconds, while the same 5 m/s north command kept being sent the entire time, the vehicle settled into a repeating oscillation roughly between 0.4m and 4m from the boundary (about a 10 second period - creeping forward, then getting pushed back) rather than converging to one stable stop point.

Proximity-based avoidance genuinely held the boundary against a continuous, ongoing attempt to breach it - a real, working safety behavior - but the steady-state result under sustained opposing input is a loose oscillating hold, not a clean stop.

Limits: one run, Copter only, simulator only; the oscillation's exact cause (control-loop interaction between the continuous velocity command and the avoidance braking correction) was not investigated further; only the fence-as-obstacle SITL backend was used, not a noisy/latent real proximity sensor model; the closer than-margin approach distance was observed, not explained.

## Parachute auto-deploy beats the thrust-loss detector's timing - but SITL doesn't model the chute slowing anything

Direct follow-up to the single motor failure test and its `thrust_loss_check` finding (too late: fired 1.8s *after* ground contact from 30m, or never fired at all from 100m). ArduCopter has a completely separate automatic safety response that had never been tried in this project before (`AP_Parachute`'s own `ap-lib` row was autotest-name-matched only, never a direct test): `Copter::parachute_check()` (`ArduCopter/crash_check.cpp`) auto-deploys the parachute if either a 30-degree attitude error or `AP_Parachute::check_sink_rate()`'s sink-rate check holds continuously for 1 second. `CHUTE_CRT_SINK` defaults to 0 (the sink-rate path is disabled out of the box), so this set it to 10 m/s; `CHUTE_ENABLED` is an `AP_PARAM_FLAG_ENABLE` parameter (the usual two-stage reboot); `CHUTE_TYPE`=10 (servo) with `SERVO9_FUNCTION`=27 (`k_parachute_release`) avoided needing a simulated relay.

`research-tools/sitl-copter-parachute-motor-failure.py` (output `sitl-evidence/copter-parachute-motor-failure/`) reused the exact same recipe as the original motor-failure test: `GUIDED` takeoff to 30m, then `SIM_ENGINE_FAIL` on the live-confirmed motor channel (channel 1, `k_motor1`). The result is a clean, directly comparable contrast: sink rate climbed smoothly from 0 past 10 m/s by about t=1.3s (the logged `vz` track shows a steady, near-linear increase, no step); `"Parachute: Released"` and `"Disarming motors"` both arrived at t=1.2s - **1.8 seconds before** `"SIM Hit ground at 17.06 m/s"` at t=3.0s. That is the opposite timing from `thrust_loss_check`'s too-late pattern in the earlier test, for the identical fault on the identical frame and altitude.

The caveat worth being honest about: SITL does not appear to simulate any actual aerodynamic braking from a released parachute. The vertical-speed track shows a smooth, continuously accelerating fall all the way to impact (0 to 17.0 m/s over the full 3.0s, no inflection after the t=1.2s release), followed by one bounce and a quick settle to rest. The only observed effect of the parachute release in this simulator was the correct detection, GCS message and disarm sequencing firing well before impact - not an actually slower landing. Whether that is a genuine SITL limitation (no chute physics modeled) or something this test simply didn't configure correctly (a chute drag/descent-rate parameter elsewhere) was not investigated further.

Limits: one run, Copter only, simulator only; only the sink-rate trigger was exercised, not the 30-degree attitude-error trigger; whether SITL has any parachute physics model at all, under any configuration, was not confirmed.

**Resolved, source-only, no new SITL run:** SITL does have a dedicated parachute simulator, `SITL::Parachute` (`libraries/SITL/SIM_Parachute.cpp`, param prefix `SIM_PARA_` - not `SIM_PARACHUTE_`), but it was never enabled in the run above (`SIM_PARA_ENABLE` defaults to 0), and it would not have changed anything if it had been: it only watches a configured PWM pin (`SIM_PARA_PIN`) and, once the signal crosses threshold, prints `"BANG! Parachute deployed"` and records a timestamp. Its own header declares `Vector3f drag() const`, but that method is never *defined* anywhere in the `.cpp` file, and the only caller of the `Parachute` object (`SIM_Aircraft.cpp`) only ever calls `update()` - `drag()` is never invoked anywhere in the codebase. The simulated parachute has zero physics effect on the aircraft in this snapshot, under any configuration: it is a logging-only stub. The 17 m/s impact in the run above was not a configuration mistake to go back and fix - it is exactly what this build's SITL parachute model does.
