# ArduBlimp frame types trace (observation)

Scope: the two ArduBlimp simulator frames in the supplied snapshot (commit `72b238201f5ea3b556e3809b2ec704fcf701474a`): `blimp` (FRAME_CLASS 1, fins; `default_params/blimp.parm`) and `blimp-motor` (FRAME_CLASS 2, motors; `default_params/blimp.parm` plus `blimp-motor.parm`). ArduBlimp has no `MAV_CMD_DO_MOTOR_TEST` handler (searching the Blimp source tree finds none) and I did not find a table to predict the output mapping from, so this is an observation, not a check against a prediction. Disposable simulators in the `Ubuntu-E` WSL distribution, simulator instance 1 (tcp 5770) beside a Plane autotest. No real vehicle.

## What was done

`research-tools/sitl-blimp-frame-outputs.py` starts each frame, reads `FRAME_CLASS` and some servo parameters, switches to MANUAL, force-arms, and overrides RC channels 1 to 4 in turn to 1900 (the others 1500) for 2 s each while recording `SERVO_OUTPUT_RAW` on the same link. An output counts as moved if it left its value at the start of that step by 20 us or more. Evidence: `sitl-evidence/blimp-frame-outputs/`.

## Observed

| Frame | FRAME_CLASS | SERVO1..3_FUNCTION (4 where read) | RC1 to 1900 | RC2 | RC3 | RC4 |
|---|---|---|---|---|---|---|
| blimp (fins) | 1 | 33, 34, 35 (SERVO4 not read) | output 4 +579 us | output 1 +654 | outputs 1 and 2 about -505 | output 3 +161, output 4 -511 |
| blimp-motor | 2 | 33, 34, 35, 36 | output 4 +200 | outputs 1 and 2 +200 | output 3 +200 | output 1 +200, output 2 -200 |

With no stick input nothing moved on either frame. The fin frame moves its outputs by roughly 500 to 650 us (its servo range is 500 to 2200 from `blimp.parm`); the motor frame by 200 us (range 1000 to 2000, `FINS_THR_MAX 0.4` in `blimp-motor.parm`). The outputs a given RC channel moves differ between the two frames, as expected from two different mixers.

What this does not say: which RC channel is roll, pitch, yaw or throttle for the blimp, what the mixing factors are, and whether the directions are right. The `SERVO4_FUNCTION`, `SERVO1_MIN`, `SERVO1_MAX` and `SERVO1_TRIM` reads of the fin frame returned nothing (the five request attempts timed out), so those values come from the default parameter file, not from the vehicle. The ArduBlimp autotest suite (7 of 7 passed, in the main ledger) is the stronger evidence for Blimp behaviour.

## Not covered

- Mixer factors and fin/motor geometry from `libraries/` and `Blimp/` source; any physical or aerodynamic behaviour.
- The Mission Planner pages for Blimp (the original motor test page is not expected to offer a motor test for it; not run).
