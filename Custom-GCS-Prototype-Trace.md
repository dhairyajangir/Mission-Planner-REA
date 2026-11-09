# Custom ground station prototype: motor test slice (simulator only)

This records what `custom-gcs/` is, what was run, what failed on the way, and what is **not** shown. It is a prototype of one function, written because the standing instruction was to "make our own version". `AGENTS.md` says the owner decides the real requirements later, so nothing here is a requirement and nothing here replaces Mission Planner. Evidence level: simulator runs on disposable SITL only; no GUI, no real aircraft, no live link.

## What exists

- `custom-gcs/customgcs/vehicle.py`: `detect(params, mav_type)` separates copter, helicopter, QuadPlane, plane, Sub, Rover, Blimp and tracker from the heartbeat vehicle type and the parameters that hold the frame (`FRAME_CLASS`/`FRAME_TYPE`, `Q_ENABLE`/`Q_FRAME_*`, `FRAME_CONFIG`).
- `custom-gcs/customgcs/motors.py`: `plan(...)` returns the `MAV_CMD_DO_MOTOR_TEST` steps for the vehicle, following the per-vehicle rules in `Copter-Frame-Types-Trace.md`, `Plane-Frame-Types-Trace.md`, `Sub-Frame-Types-Trace.md`, `Rover-Frame-Types-Trace.md` and `Vehicle-Motor-Test-Page-Trace.md`:
  - Copter and QuadPlane: param1 = test sequence, order from 45 matrix layouts generated from `AP_MotorsMatrix.cpp` (`custom-gcs/tools/gen_matrix_layouts.py`, data in `customgcs/data/matrix_layouts.json`; includes types such as Y4 that Mission Planner's `APMotorLayout.json` lacks); the output a motor is on comes from the vehicle's own `SERVOn_FUNCTION`. The tricopter sequence is hand-transcribed from `AP_MotorsTri.cpp`.
  - Sub: board-order test, zero-based outputs, armed, repeated within 500 ms.
  - Rover: 1 throttle, 2 steering, 3 left, 4 right (5, main sail, is not offered because the snapshot rejects it).
  - Helicopter, plane, Blimp, tracker and scripted matrix classes raise `Unsupported`.
- `custom-gcs/customgcs/link.py` and `__main__.py`: pymavlink link, whole-list parameter download, plan runner that compares the servo outputs that actually moved on `SERVO_OUTPUT_RAW` with the planned ones; `python -m customgcs info|plan|motor-test`.
- Tests: 19 pytest cases (`custom-gcs/tests/`): 17 plan/detection cases whose expected orders are orders the simulator produced earlier, and 2 for the rejection-retry path using a fake link. Run in the `Ubuntu-E` venv because pymavlink is only installed there.

## Integration runs (ten disposable simulators, one run each per attempt)

`custom-gcs/integration/run-integration.sh` starts each simulator, runs `motor-test`, stops it. Frames: Copter quad-plus, hexa-x, octa, y6, tri; QuadPlane quadplane, quadplane-tri; Sub vectored; Rover rover-skid, sailboat.

| Attempt | Evidence | Result |
|---|---|---|
| 1 | `sitl-evidence/custom-gcs-integration-run1-surfaces-counted-and-not-ready/` | Copter 5 of 5 and Sub matched. QuadPlane mismatched because the checker counted control-surface servos that move by themselves; Rover mismatched because it started too early. Both were faults of the checker, not of the plans. Kept. |
| 2 | `sitl-evidence/custom-gcs-integration-run2-rover-rejected-while-initialising/` | After limiting the check to motor, throttle, tilt and steering outputs and waiting for a heartbeat status of STANDBY or higher: Copter, QuadPlane and Sub matched; rover-skid 3 of 4 and sailboat 2 of 4 mismatched. Kept. |
| probe | `sitl-evidence/rover-ready-probe/`, `research-tools/sitl-rover-ready-probe.py` | Rover's heartbeat reports status ACTIVE (4) from the first message, so waiting for it says nothing. The vehicle answers `MAV_CMD_DO_MOTOR_TEST` with COMMAND_ACK result 4 ("Motor Test: Board initialising", then "Arm: Accels inconsistent") for about 12 to 15 s after the first heartbeat, then accepts. Probed every 5 s, so the readiness moment is only known to within 5 s; the simulator is SITL, real boards take other times. |
| 3 | `sitl-evidence/custom-gcs-integration/` | After replacing the status wait by reading each COMMAND_ACK and re-sending a rejected step for up to 60 s: **all ten matched** (copter 4 of 4, 6 of 6, 8 of 8, 6 of 6, 4 of 4; QuadPlane 4 of 4 twice; Sub 6 of 6; Rover 4 of 4 twice). Rover's first step took 4 tries on both frames and says so in its note. |

## What this does and does not show

- Shown: for those ten simulated frames, the plan the prototype derives from the vehicle's own parameters moves exactly the predicted outputs, in the predicted order, with the prototype's own ACK handling.
- Not shown: any other frame (the earlier sweeps cover more), any flight, any real autopilot or motor, any GUI, calibration, parameter editing, mission or map function. Helicopter, plane, Blimp and scripted matrices are explicitly unsupported. The unit-test orders and the integration orders come from the same earlier sweeps, so a shared misreading would not be caught by either.
- The check `moved` uses a 20 microsecond change threshold on `SERVO_OUTPUT_RAW` and ignores outputs that are not motor, throttle, tilt or steering functions; a failure to move something outside that set is not detected.
- The motor test spins motors. It was run against simulators only and must not be run with propellers fitted or against a real aircraft.
