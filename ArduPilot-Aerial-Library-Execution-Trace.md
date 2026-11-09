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

**Not reached in these flights:** `AP_YawController::get_rate_out` (Plane) and `AP_LandingGear::update` (Copter; the Copter has no landing gear enabled).

## Modes

- **`ArduCopter/mode_acro_heli.cpp`**: `ModeAcro_Heli` exists only in the helicopter build (`nm` shows 8 symbols in `arducopter-heli` and none in `arducopter`). In that build ACRO was accepted twice (disarmed and with the arm refused) and the log's `MODE` message shows mode 1 (ACRO) at 49.4 s with reason 2 (a ground-station command). The class was entered and its `run` was called by the main loop on the ground; no flight was made, so the heli-specific control (virtual flybar, acro rates) was not exercised.
- **`ArduCopter/mode_guided_custom.cpp`**: the only way into it is a script that registers a custom mode. With `Flip_Mode.lua` (mode number 100, `vehicle:register_custom_mode`), requests for mode 100 on the ground were refused by the class with the vehicle's text "Mode change to Flip 2 failed: init failed" (the mode's registered name appears in the refusal, so `ModeGuidedCustom::init` ran and returned false), and in flight from ALT_HOLD the request was accepted: the log's `MODE` messages show mode 100 at 79.6 s (reason 2) and a return to ALT_HOLD at 82.2 s (reason 32; I did not look up what that reason code means), 2.6 s later. What the script did in those 2.6 s (a flip's attitude and throttle) was not checked.

## Faults and limits

- The first version of the library map missed the `TECS` and `RFR*` writers because their declarations are multi-line or written in a shape the search did not expect; they were found by a direct search of the source and are listed above with their file and line. The map file keeps its output as generated.
- The helicopter could not be armed (motor interlock), so nothing about helicopter flight dynamics was observed.
- One flight per vehicle; the library evidence is "ran", not "ran correctly".
- The gdb runs add real-time delay only at each function's first hit; flight timing is otherwise as without gdb, but a debugger could change timing in ways I did not measure.
