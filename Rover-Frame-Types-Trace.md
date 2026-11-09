# ArduRover frame types trace

Scope: what ArduRover's motor test does for each Rover simulator frame in the supplied snapshot (commit `72b238201f5ea3b556e3809b2ec704fcf701474a`), on disposable ArduRover simulators in the `Ubuntu-E` WSL distribution. Nothing here is a real vehicle. The sweep ran on simulator instance 1 (tcp 5770) beside a Plane autotest on instance 0.

## How the Rover motor test works

From `Rover/motor_test.cpp`, `Rover/GCS_MAVLink_Rover.cpp` and `libraries/AR_Motors/AP_MotorsUGV.cpp`: `MAV_CMD_DO_MOTOR_TEST` param1 selects what to test: 1 throttle, 2 steering, 3 throttle left, 4 throttle right, 5 main sail (`AP_MotorsUGV::motor_test_order`). The test drives every output whose `SERVOn_FUNCTION` matches: throttle (70) or motor1 (33) for 1; steering (26) or motor2 (34) for 2; throttle left (73) or motor3 (35) for 3; throttle right (74) or motor4 (36) for 4; main sail sheet (89), wing sail elevator (128) or mast rotation (137) for 5. It arms the vehicle and switches off the GCS, throttle and crash failsafes while the test runs.

So the tested outputs depend on the frame's servo function assignment, which comes from the frame's default parameter files.

## Sweep

`research-tools/sitl-rover-frame-motor-sweep.py` (run by `research-tools/run-rover-frame-motor-sweep.sh`) starts each frame (`--model <frame>`), reads `SERVO1_FUNCTION` to `SERVO16_FUNCTION` from the vehicle, sends the test for param1 = 1 to 5 (50 percent, 2 s), records `SERVO_OUTPUT_RAW`, and compares the outputs that moved with the outputs those function values predict. The prediction comes from the same vehicle's parameters, not from a table of mine.

| Frame | Servo functions on outputs 1 to 6 | Tests 1 to 4 | Test 5 (main sail) |
|---|---|---|---|
| rover | 26 (steering), 0, 70 (throttle), 0, 0, 0 | match: throttle moves output 3, steering output 1 | nothing to move |
| rover-skid | 73, 0, 74, 0, 0, 0 | match: left output 1, right output 3 | nothing to move |
| rover-omni3mecanum | 33, 34, 35, 0, 0, 0 | match: motor1, motor2, motor3 on outputs 1, 2, 3; test 4 moves nothing | nothing to move |
| rover-vectored | same as rover | match | nothing to move |
| balancebot | same as rover-skid | match | nothing to move |
| motorboat, motorboat-skid | same as rover, rover-skid | match | nothing to move |
| sailboat | 26, 0, 70, 89 (main sail), 137 (mast rotation), 0 | match | **does not move** |
| sailboat-motor | 26, 0, 70, 89, 0, 0 | match | **does not move** |

Of the 45 tests (nine frames, five tests each), 43 did exactly what the vehicle's own function values predicted (all 36 throttle, steering, left and right tests, and 7 main-sail tests that had nothing to move); the other 2 are the sailboat main-sail tests below. Evidence: `sitl-evidence/rover-frame-motor-sweep/` (`rover-sweep-summary.csv`, `rover-sweep-per-test.csv`, simulator logs).

### The main sail test cannot be started over MAVLink

For the two sailboat frames the vehicle answered `Motor Test: invalid motor (5)` and no output moved. Reading the source: `Rover::mavlink_motor_test_check` rejects any sequence above `AP_MotorsUGV::MOTOR_TEST_THROTTLE_RIGHT` (4), while `AP_MotorsUGV::output_test_pct` has a `MOTOR_TEST_MAINSAIL` (5) case that drives the sail outputs. So that case is unreachable through `MAV_CMD_DO_MOTOR_TEST` in this snapshot, and a ground station cannot test the main sail, wing sail elevator or mast rotation outputs with it. I did not check whether another path (for example the pilot stick through the pass-through type) reaches the sail case, and I have not looked at the upstream history for this.

## Not covered

- Gazebo, AirSim and calibration frames (external simulators).
- Thruster or wheel direction, the `MOT_*` parameters, the actual vehicle behaviour on the ground or in water.
- The Mission Planner motor test page for Rover (the page's source returns four motors for ground rovers and boats; not run).
- Rover-specific flight-mode behaviour; the Rover autotest suite results are in the main ledger (137 of 138).
