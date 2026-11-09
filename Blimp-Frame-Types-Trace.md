# ArduBlimp frame types trace

Scope: the two ArduBlimp simulator frames in the supplied snapshot (commit `72b238201f5ea3b556e3809b2ec704fcf701474a`): `blimp` (FRAME_CLASS 1, fins; `default_params/blimp.parm`) and `blimp-motor` (FRAME_CLASS 2, motors; `default_params/blimp.parm` plus `blimp-motor.parm`). ArduBlimp has no `MAV_CMD_DO_MOTOR_TEST` handler (searching the Blimp source tree finds none). I first ran the stick test below as a plain observation; I then found the mixer in `Blimp/Fins.cpp` and compared the observations with it (section "Check against the mixer"), so the comparison was made after the fact, not as a blind prediction. Disposable simulators in the `Ubuntu-E` WSL distribution, simulator instance 1 (tcp 5770) beside a Plane autotest. No real vehicle.

## What was done

`research-tools/sitl-blimp-frame-outputs.py` starts each frame, reads `FRAME_CLASS` and some servo parameters, switches to MANUAL, force-arms, and overrides RC channels 1 to 4 in turn to 1900 (the others 1500) for 2 s each while recording `SERVO_OUTPUT_RAW` on the same link. An output counts as moved if it left its value at the start of that step by 20 us or more. Evidence: `sitl-evidence/blimp-frame-outputs/`.

## Observed

| Frame | FRAME_CLASS | SERVO1..3_FUNCTION (4 where read) | RC1 to 1900 | RC2 | RC3 | RC4 |
|---|---|---|---|---|---|---|
| blimp (fins) | 1 | 33, 34, 35 (SERVO4 not read) | output 4 +579 us | output 1 +654 | outputs 1 and 2 about -505 | output 3 +161, output 4 -511 |
| blimp-motor | 2 | 33, 34, 35, 36 | output 4 +200 | outputs 1 and 2 +200 | output 3 +200 | output 1 +200, output 2 -200 |

With no stick input nothing moved on either frame. The fin frame moves its outputs by roughly 500 to 650 us (its servo range is 500 to 2200 from `blimp.parm`); the motor frame by 200 us (range 1000 to 2000, `FINS_THR_MAX 0.4` in `blimp-motor.parm`). The outputs a given RC channel moves differ between the two frames, as expected from two different mixers.

## Check against the mixer (`Blimp/Fins.cpp`, `Blimp/radio.cpp`, `Blimp/mode_manual.cpp`)

- RC channels: RC1 (roll channel) is "right", RC2 (pitch channel) is "front", RC3 (throttle channel) is "up" and the pilot's down axis is its negative (`pilot.z = -channel_up`), RC4 (yaw channel) is yaw. MANUAL passes them to the mixer scaled by `g.max_man_thr`.
- Motor frame (FRAME_CLASS 2, `setup_motors`): output 1 = front +1, yaw +1; output 2 = front +1, yaw -1; output 3 = down -1; output 4 = right +1. Observed: RC1 moved output 4 only; RC2 moved outputs 1 and 2 together; RC3 moved output 3 only; RC4 moved output 1 up and output 2 down. All four match.
- Fin frame (FRAME_CLASS 1, `setup_fins`, amplitude factors then offset factors per fin: back, front, right, left): fin 1 (back) has front amplitude +1 and down amplitude and offset 0.5; fin 2 (front) has front amplitude -1 and down amplitude and offset 0.5; fin 3 (right) has right amplitude -1 and yaw amplitude and offset 0.5; fin 4 (left) has right amplitude +1 and yaw amplitude 0.5 and offset -0.5. Observed: RC1 (positive right) moved output 4 (the left fin, the one with positive right amplitude); RC2 moved output 1 (the back fin, positive front amplitude); RC3 moved outputs 1 and 2 (both fins with a down term); RC4 moved output 3 up and output 4 down (opposite yaw offsets). All four match in which outputs move and in the sign pattern.
- Not compared: the size of the movements (the fin outputs are a sine wave around an offset, sampled once at the end of each step, so the numbers above are one sample), thruster or fin geometry, and any in-air behaviour.

The `SERVO4_FUNCTION`, `SERVO1_MIN`, `SERVO1_MAX` and `SERVO1_TRIM` reads of the fin frame returned nothing (the five request attempts timed out), so those values come from the default parameter file, not from the vehicle. The ArduBlimp autotest suite (7 of 7 passed, in the main ledger) is the stronger evidence for Blimp behaviour.

## Not covered

- Fin and motor geometry, the sizes of the movements, and any physical or aerodynamic behaviour.
- The Mission Planner pages for Blimp other than the motor test page, which is disabled for the Blimp simulator (`Vehicle-Motor-Test-Page-Trace.md`).
