# Motor test page trace

Scope: the original Mission Planner 1.3.83 `ConfigMotorTest` page driven against a disposable ArduCopter SITL, with an independent observer watching the vehicle's motor outputs. `research-tools/PageMotorTestProbe.cs` connects `MainV2.comPort` over TCP to SERIAL0 (port 5760), builds the page from the original `MissionPlanner.exe` (data-redirected isolated copy), calls `Activate()`, sets the throttle box to 10 percent and the duration box to 2 s, and calls the page's own button handlers by reflection: `but_TestAll`, `but_TestAllSeq` and `but_StopAll`. In parallel `research-tools/sitl-servo-observer.py` (pymavlink on SERIAL1, port 5762) records `SERVO_OUTPUT_RAW` at 10 Hz and the vehicle's `STATUSTEXT`. `research-tools/run-motor-test-probe.ps1` runs both; `research-tools/analyze-motor-test.py` lines the action times up with the outputs. A probe harness is driving the page, not a person clicking; simulator only, no hardware and no propellers involved.

Evidence: `sitl-evidence/motor-test-page/` (page action log, observer CSV and STATUSTEXT, summary CSV, console, simulator log).

## Results

| Page action | What the independent observer saw |
|---|---|
| `but_TestAll` (all four motors, 10 percent, 2 s) | All four servo outputs rose from 1000 to 1100 microseconds (10 percent of the 1000 to 2000 range) and fell back; the vehicle reported "starting motor test" within 6 ms of the action and "finished motor test" 2.05 s later. |
| `but_TestAllSeq` (sequence, 2 s each) | Servo outputs rose one at a time in the order servo3, servo1, servo4, servo2, about 3.0 s apart (2 s on plus a 1 s gap), 0.1 s, 3.1 s, 6.1 s and 9.1 s after the action. |
| `but_StopAll` (zero throttle to every motor) | All four outputs stayed at 1000; the vehicle logged a start and finish message per motor. |

No message box was raised (the harness logs them; none appeared), so the page's "Command was denied by the autopilot" path did not trigger.

## Check against the source

- `ArduCopter/motor_test.cpp` (`motor_test_output`) runs each motor for the timeout, then holds the minimum output for half the timeout before moving to the next sequence number, which gives the 2 s plus 1 s spacing; percent throttle maps to `pwm_min + (pwm_max - pwm_min) * percent / 100`, giving 1100 for 10 percent.
- The simulator was started with `-M +` (a quad plus model). The plus-frame table in `libraries/AP_Motors/AP_MotorsMatrix.cpp` gives test orders motor1 = 2, motor2 = 4, motor3 = 1, motor4 = 3, so sequence 1 to 4 is motor3, motor1, motor4, motor2, which is the observed order. I did not read `FRAME_TYPE` from the vehicle; the match with the plus table is the evidence the frame was plus.
- My first expectation used the X-frame table and predicted 1, 4, 2, 3; it was wrong because the frame was plus, not because the vehicle misbehaved.

## Not covered

The page's per-motor buttons, the MOT_SPIN_ARM and MOT_SPIN_MIN buttons, the frame picture that the page draws from the vehicle's frame parameters, motor test on other frames or vehicle types, and the unmodified GUI driven by a person. Only one frame (plus) was observed.
