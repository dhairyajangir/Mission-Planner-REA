# customgcs: first slice of a replacement ground station (prototype)

**Status: prototype, simulator only.** This is not a finished ground station and does not replace Mission Planner. `AGENTS.md` says the owner will decide the real requirements later; this slice was written because the original instruction was to build "our own version", and it picks the one area where the evidence in this archive says Mission Planner 1.3.83 is weakest and best understood: motor tests across vehicle and frame types. It has only been run against disposable simulators, never a real aircraft; the motor test spins motors and must not be run with propellers on.

## What it does

- `customgcs.vehicle.detect(params, mav_type)`: tells copter, helicopter, QuadPlane, plane, Sub, Rover, Blimp and tracker apart, and names the parameters that hold the frame (`FRAME_CLASS`/`FRAME_TYPE`, `Q_FRAME_*`, `FRAME_CONFIG`).
- `customgcs.motors.plan(info, params)`: plans a correct motor test for the vehicle from facts recorded in the traces:
  - Copter and QuadPlane: test sequence 1..N from the firmware's own testing-order tables (`customgcs/data/matrix_layouts.json`, 45 layouts generated from `AP_MotorsMatrix.cpp`, including types Mission Planner's own `APMotorLayout.json` lacks such as Y4), and the servo output each motor is on, read from the vehicle's `SERVOn_FUNCTION` values.
  - Sub: board-order test with zero-based outputs, armed, repeated within 500 ms.
  - Rover: throttle, steering, throttle left, throttle right, on the outputs with the matching servo function.
  - Single and coax copters: six sequences (four flap servos, two motors).
  - Helicopter: no plan; the firmware refuses the test ("Motor Test: Disabled on heli").
  - Anything else (plane, Blimp, tracker, scripted matrices that need their Lua script) raises `Unsupported` rather than guessing.
- `customgcs.link`: connects with pymavlink, downloads the whole parameter list, runs the plan and reports which servo outputs actually moved against what was expected.
- `python -m customgcs info|plan|motor-test --port 5760 [--pct 10] [--arm]`.

## Evidence

- `tests/test_plans.py`: unit tests, each expected order taken from an order the simulator actually produced (see `Copter-Frame-Types-Trace.md`, `Plane-Frame-Types-Trace.md`, `Sub-Frame-Types-Trace.md`, `Rover-Frame-Types-Trace.md`). Run `python -m pytest` in this folder (22 tests; the two retry tests need pymavlink).
- `integration/run-integration.sh` runs `motor-test` against ten disposable simulators in the `Ubuntu-E` WSL distribution; the third attempt (`../sitl-evidence/custom-gcs-integration-run3-ten-simulators-all-matched/`) matched all ten and the fourth (`../sitl-evidence/custom-gcs-integration/`, adds Copter single and coax and the helicopter) matched every plannable frame. The first two attempts had faults in the verification and are kept in `../sitl-evidence/custom-gcs-integration-run1-surfaces-counted-and-not-ready/` and `../sitl-evidence/custom-gcs-integration-run2-rover-rejected-while-initialising/`. `integration/run_all_layouts.py` ran every generated Copter layout (41 of 43 matched; the two NYT types exist only in ArduPlane builds, see the trace; results in `../sitl-evidence/custom-gcs-all-layouts/`). See `../Custom-GCS-Prototype-Trace.md`.
- `tools/gen_matrix_layouts.py` regenerates `matrix_layouts.json` from a supplied ArduPilot tree.

## What it does not do

No map, mission planning, parameter editing UI, calibration, firmware handling, telemetry display, logs, or any user interface at all; no real hardware. The tricopter sequence is hand-transcribed from `AP_MotorsTri.cpp` (the file is generated for the matrix classes only). The integration run covers ten frames, not every frame.
