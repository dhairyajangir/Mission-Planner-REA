# Aerial mode entry and arming requirements seen in the simulator

What had to be true before ArduPilot's copter, plane and helicopter builds accepted a mode request or an arm command, collected from the simulator runs in this repository. Everything here is **simulated** (WSL, the pinned snapshot `72b238201f5ea3b556e3809b2ec704fcf701474a`, SITL builds, one run each unless stated); nothing was checked on an aircraft, and "accepted" means the vehicle acknowledged the request and its heartbeat reported the mode, not that the mode flew well. The detail and the evidence files are in `ArduPilot-Aerial-Library-Execution-Trace.md` and the folders named below. A custom ground station should treat this as a list of things to check and tell the user, not as a guarantee.

## Arming

| Situation | What the vehicle said or did | Where seen |
|---|---|---|
| Helicopter, motor-interlock RC switch high at arming | arm refused: `Motor Interlock Enabled` (the switch must be low to arm, then high to run the rotor; `RC8_OPTION` 32 in the default heli parameters) | `sitl-evidence/aerial-library-evidence/heli-acro.json`, `sitl-evidence/heli-flight/` |
| Helicopter, interlock raised after arming | `RC8: MotorInterlock HIGH`, then `Runup Complete` after the rotor run-up (`H_RSC_RUNUP_TIME` 10 s) | `sitl-evidence/heli-flight/` |
| Helicopter, `AROT_ENABLE` 1 without `H_RSC_AROT_ENBL` | arm refused: `PreArm: AROT: H_RSC_AROT_* not configured` | `sitl-evidence/heli-autorotate-run1-prearm-rsc-not-configured/` |
| Plane, throttle channel held above minimum (RC override at 1500) | arm refused (ack result 4) | `sitl-evidence/plane-soar-autoland-run1-arm-refused-throttle-up/` |
| Plane, a soaring switch on channel 8 (`RC8_OPTION` 88) | arm refused: `Arm: Mode channel and RC8_OPTION conflict` (channel 8 is the Plane's flight-mode channel here) | `sitl-evidence/plane-soar-run3-rc8-option-conflict/` |
| Copter, AUTO mode requested before the position estimate is ready | AUTO refused until the estimate converged | `Custom-GCS-Prototype-Trace.md` |
| Copter armed in AUTO on the ground | disarms after `DISARM_DELAY` (10 s) unless the mission is started with `MAV_CMD_MISSION_START`; a Copter will not arm in AUTO | `Custom-GCS-Prototype-Trace.md` |

## Copter modes entered in the air (simulator)

| Mode | Result | Condition seen | Evidence |
|---|---|---|---|
| DRIFT, SPORT, ACRO | accepted from AUTO in flight | with no stick input the Copter fell in DRIFT (ground contact 14.7 m/s in the first run); sticks centred and throttle 1500 by RC override fixed it | `sitl-evidence/copter-untested-modes/`, `...-run1-no-rc-input-fell/` |
| GUIDED_NOGPS | accepted | a level attitude target stream was sent | same |
| SYSTEMID | accepted | `SID_AXIS` 1, requested from STABILIZE (needs a mode with manual throttle) and flying; the source's refusal texts are `Aircraft must be flying`, `Axis requires manual throttle` and `No axis selected, SID_AXIS = 0` (read from `mode_systemid.cpp`; only the accepted case was run) | same |
| TURTLE | accepted by `research-tools/sitl-copter-turtle-entry.py` (no gdb) with `SERVO_DSHOT_ESC` 1 and RC channels 1 to 4 at 1500, reproduced at speedups 5 and 1; text `Turtle: raise throttle to arm`. Refused in six attempts of my other harness (five under gdb, one without) | needs a DShot ESC type, disarmed, sticks centred; why my harness is refused is **not determined** (see the trace) | `sitl-evidence/copter-turtle-entry/`, `copter-turtle-entry-recheck/`, `copter-turtle-entry-recheck-s1/` and the other `copter-turtle-*` folders |
| AUTOROTATE | helicopter build only | `AROT_ENABLE` 1 and `H_RSC_AROT_ENBL` 1, armed and flying; with `AROT_ENABLE` 0 refused | `sitl-evidence/heli-autorotate/` |

## Plane and QuadPlane modes

All 24 modes of a QuadPlane build were requested from AUTO in flight (`sitl-evidence/plane-inflight-modes/`): 22 accepted, THERMAL and AUTOLAND refused there. Two further conditions:

- **AUTOLAND**: not available on a QuadPlane (`autoland not available`); needs the plane to be flying (`Must already be flying!`) and the takeoff direction to have been captured by a takeoff (`Takeoff initial direction not set`). On a plain Plane after a mission takeoff it was accepted and flew approach, glide slope, flare and touchdown (`sitl-evidence/plane-soar-autoland-run2-autoland-ok-soar-arm-refused/`).
- **THERMAL**: needs `SOAR_ENABLE` 1 (an enable flag that takes a reboot) and the pilot soaring switch off its low position (`RC7_OPTION` 88 and channel 7 in the middle gave `Soaring: Enabled, manual mode changes`); it left THERMAL after 2 s at the minimum soaring altitude (`sitl-evidence/plane-soar/`).
- **ACRO yaw rate controller**: `YAW_RATE_ENABLE` 1 and `ACRO_YAW_RATE` above zero are needed before `AP_YawController::get_rate_out` is used in ACRO (`sitl-evidence/plane-gaps/`).
- **QuadPlane**: VTOL takeoff, forward transition (`Transition started`, `Transition airspeed reached`, `Transition done`), waypoints and a VTOL landing ran by mission (`sitl-evidence/plane-gaps/quadplane-summary.txt`).

## Helicopter modes

With the interlock handled as above: ACRO, STABILIZE, ALT_HOLD and LOITER accepted from AUTO in the air; AUTOROTATE accepted only with the two autorotation parameters set (`sitl-evidence/heli-flight/`, `sitl-evidence/heli-autorotate/`).

## Precision landing (Copter)

`PLND_ENABLED` 1 with `PLND_TYPE` 4 (SITL) or 2 (IRLock), a rangefinder and the simulator's `SIM_PLD_*` target: the Copter landed 0.98 m from a target 4 m north and 4 m west of home in both cases (the same coordinates, so not independent); see `sitl-evidence/copter-precland/`.

## What this page does not say

Nothing here covers a real aircraft, real sensors, wind, a radio link or a battery. Each item is one run; the refusal texts are the vehicle's own words as captured, and some refusals gave no text (TURTLE, THERMAL and AUTOLAND on a QuadPlane via the acknowledgement only). Rover, Sub, Blimp and the Mission Planner side are outside this page.
