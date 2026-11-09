# ArduSub frame configurations trace

Scope: what ArduSub does for each `FRAME_CONFIG` value in the supplied snapshot (commit `72b238201f5ea3b556e3809b2ec704fcf701474a`), checked with the motor test on disposable ArduSub simulators in the `Ubuntu-E` WSL distribution. Nothing here is a real vehicle or thruster. The sweep ran on simulator instance 1 (tcp 5770) beside a Plane autotest on instance 0.

## How the Sub motor test differs from the Copter one

From `ArduSub/motors.cpp` and `ArduSub/GCS_MAVLink_Sub.cpp`:

- Only the "board order" test type is accepted (`MAV_CMD_DO_MOTOR_TEST` param6 = 2); the vehicle must be armed; the safety switch must not be disarmed; the throttle type "pilot" is rejected.
- The command has to be repeated at least every 500 ms (`verify_motor_test`): after that the test ends with "Motor test timed out!", the vehicle is disarmed, and a ten second cooldown starts.
- Param1 is a **zero-based output number**: `AP_MotorsMatrix::output_test_num(output_channel, pwm)` checks `motor_enabled[output_channel]` and calls `rc_write(output_channel, pwm)`, so param1 = n drives servo output n + 1. There is no sequence or testing-order step as in Copter, and the `testing_order` argument of `add_motor_raw_6dof` is not used by it.

## Sweep

`research-tools/sitl-sub-frame-motor-sweep.py` (run by `research-tools/run-sub-frame-motor-sweep.sh`): for each `FRAME_CONFIG` 0 to 7 it starts a simulator, sets `FRAME_CONFIG`, restarts without wiping parameters, force-arms, sends the test for param1 = 0 to 11 at 10 percent (every 0.25 s for 1.4 s, back to back with the next output) and records `SERVO_OUTPUT_RAW` on the same link. An output counts as moved if it left its value at the start of that window by 20 us or more. The expected motors come from the `add_motor_raw_6dof(AP_MOTORS_MOT_n, ...)` lines of `AP_Motors6DOF.cpp` in the same tree.

| FRAME_CONFIG | Name | Motors defined in the source | Outputs that moved for their own number | Result |
|---|---|---|---|---|
| 0 | BLUEROV1 | 1 to 6 | 1 to 6 | match |
| 1 | VECTORED | 1 to 6 | 1 to 6 | match |
| 2 | VECTORED_6DOF | 1 to 8 | 1 to 7 with default parameters; 1 to 8 with `SERVO8_FUNCTION=40` | match once servo 8 is a motor |
| 3 | VECTORED_6DOF_90DEG | 1 to 8 | same as 2 | match once servo 8 is a motor |
| 4 | SIMPLEROV_3 | 1 to 3 | 1 to 3 | match |
| 5 | SIMPLEROV_4 | 1 to 5 | 1 to 5 | match |
| 6 | SIMPLEROV_5 | 1 to 5 | 1 to 5 | match |
| 7 | CUSTOM | 1 to 3 (falls through to SIMPLEROV_3) | 1 to 3 | match |

No output other than the tested one moved in any test. Evidence: `sitl-evidence/sub-frame-motor-sweep/` (all eight configurations, default parameters) and `sitl-evidence/sub-frame-motor-sweep-servo8-motor8/` (configurations 2 and 3 with `SERVO8_FUNCTION=40`, i.e. Motor8).

**Finding.** With the simulator's default Sub parameters (`default_params/sub.parm`), servo output 8 has `SERVO8_FUNCTION = 7`, which is not a motor function. Selecting an eight-thruster frame (`FRAME_CONFIG` 2 or 3) therefore leaves the eighth thruster without an output: the motor test for it moves nothing until `SERVO8_FUNCTION` is set to Motor8 (40). The extra frame file `sub-6dof.parm` that the simulator uses for `vectored_6dof` only sets `FRAME_CONFIG` among the servo-related parameters. I did not look at how a real vehicle is normally configured, or at what the default function 7 is meant to be; this is what the simulator does with its own defaults.

## Run history, kept

- `sub-frame-motor-sweep-run1-test-timed-out/`: my first version left 0.5 s of silence between outputs, exactly the timeout, so the vehicle ended the test and disarmed after the first output; only output 1 appeared to move and the run is not valid.
- `sub-frame-motor-sweep-run2-one-based-numbers/`: the second version kept the commands flowing but numbered the outputs from 1 and measured against the idle values, so every earlier output stayed deviated and each test seemed to move several outputs, shifted by one. That is what showed that param1 is zero-based; not valid either.
- The valid runs are the two folders named in the table.

## Not covered

- The Mission Planner pages for Sub (the original motor test page is expected to be disabled for ArduSub because the vehicle has no `FRAME`, `FRAME_TYPE` or `Q_FRAME_TYPE` parameter; not yet run).
- Thruster direction (`MOT_n_DIRECTION`), the mixing factors, or any in-water behaviour. The sweep checks only which output a test number drives.
- The `gazebo-bluerov2` simulator frame (needs an external simulator).
