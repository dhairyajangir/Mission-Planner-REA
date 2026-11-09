# ArduPlane trace: autotest suite and QuadPlane frame motor test

Scope: ArduPilot's own `Plane` autotest suite and a QuadPlane motor test over the VTOL frames, in the supplied snapshot (commit `72b238201f5ea3b556e3809b2ec704fcf701474a`), on disposable simulators in the `Ubuntu-E` WSL distribution. Nothing here is a real aircraft, motor or propeller.

## 1. The Plane autotest suite

Run with `research-tools/run-autotest.sh` against the pinned snapshot copy (default debug build, speedup 10, `--timeout=40000`), started detached at 05:22 UTC and finished at 08:02 UTC the same day (2 h 40 min). Result (`sitl-evidence/autotest-plane/Plane-run1.log.gz`, `autotest-results.csv`): **250 passed, 1 failed** (`FlyEachFrame`).

- The failure: `FlyEachFrame` raised `Expected MAV_RESULT_ACCEPTED got MAV_RESULT_FAILED` at frame `plane-elevrev`, where the arm command was refused with "Arm: Logging not started". The frames before it flew through.
- Rerun alone, with nothing else running (`Plane-fef-alone1.log.gz`): **passed**, all 31 listed frames in 678 s, including `plane-elevrev`. So the failure did not repeat. I ran Sub, Rover and Blimp sweeps on a second simulator instance beside the suite during its run, which may have loaded the machine at that moment, but I cannot show that is the cause; one passing rerun does not exclude an intermittent fault. The full-suite log of the failing run is kept (`ArduPlane-FlyEachFrame-in-full-suite.txt.gz`) next to the rerun's.
- The suite includes the QuadPlane tests, the tailsitter, soaring, AFS (advanced failsafe), parachute, airspeed-driver and landing tests; the per-test list is in `autotest-results.csv`.
- Results parsing note: for some tests the collected description contains commas, so a naive column split of `autotest-results.csv` shows garbage in the result column for them; read it with a CSV reader (the builders do).

`FlyEachFrame` in the Plane suite lists the 31 frames in `vehicleinfo.json` for ArduPlane; external simulators (`gazebo-zephyr`, `CRRCSim`, `jsbsim`, `last_letter`, `scrimmage-plane`, `calibration`) are passed over by the test.

## 2. QuadPlane motor test across VTOL frames

`research-tools/sitl-frame-motor-sweep.py` with `SWEEP_BINARY=arduplane SWEEP_PARAM_PREFIX=Q_` (run by `research-tools/run-frame-motor-sweep.sh`): for each frame it starts the simulator, reads `Q_FRAME_CLASS` and `Q_FRAME_TYPE`, and sends `MAV_CMD_DO_MOTOR_TEST` for sequence 1..N (10 percent, 1 s each) while recording `SERVO_OUTPUT_RAW`. The vehicle must be disarmed; the test uses the same `output_test_seq` mechanism as ArduCopter (`ArduPlane/motor_test.cpp`).

The expected order comes from the `AP_MotorsMatrix.cpp` tables (or, for the tri classes, the hand-transcribed `AP_MotorsTri` sequence 1, 4, tail, 2), with each motor number mapped to the output whose `SERVOn_FUNCTION` is that motor's function, read from the vehicle: on these frames motor 1 is on servo 5, not servo 1. For a tailsitter (class 10) the test of `AP_MotorsTailsitter` addresses the throttle-right (74), tilt-right (76), throttle-left (73) and tilt-left (75) functions.

| Frame | Q_FRAME_CLASS / TYPE | Motor to output | Sequence 1..N moved outputs | Result |
|---|---|---|---|---|
| quadplane, quadplane-tilt | 1 / 1 | 1 to 5, 2 to 6, 3 to 7, 4 to 8 | 5, 8, 6, 7 | 4 of 4 match |
| quadplane-tilthvec | 1 / 3 | same | 5, 8, 6, 7 | 4 of 4 |
| quadplane-copter_tailsitter | 1 / 0 | same | 7, 5, 8, 6 | 4 of 4 (plus frame order) |
| quadplane-tri, -tilttri, -tilttrivec, -cl84 | 7 / 1 | 1 to 5, 2 to 6, 4 to 8, tail 7 to 11 | 5, 8, 11, 6 | 4 of 4 |
| firefly | 5 / 11 (Y6F) | 1 to 3 through 6 to 8, tail 7 to 11 | 4, 7, 3, 6, 5, 8 | 6 of 6 |
| quadplane-ice | 1 / 1 | only motors 1 and 2 have outputs (5, 6) | 5, none, 6, none | 2 of 4 (see below) |
| plane-tailsitter | 10 / 1 | outputs are aileron, elevator, throttle (70), rudder | none | nothing to move (see below) |

- `quadplane-ice`: the frame is a quad, but its default parameters assign motor functions to only two outputs, so the tests for motors 3 and 4 (sequence 2 and 4 in the X order) move nothing. This is what the default parameter files do; I did not look at why. **Later check (not reproduced):** a fresh `quadplane-ice` simulator read by single-name requests and by the full list, 3 s and 20 s after start, has all four motors on outputs 5 to 8 (`sitl-evidence/custom-gcs-special-cases/quadplane-ice.txt`, 4 of 4 matched), so this paragraph may describe a state of that sweep run I cannot reconstruct; see `Custom-GCS-Prototype-Trace.md`.
- `plane-tailsitter`: this model's servo functions are aileron (4), elevator (19), throttle (70) and rudder (21); none of the outputs the tailsitter test addresses (throttle left/right, tilt left/right) exist on it, so the motor test is accepted and moves nothing. Class 10 here is the single-motor tailsitter, and the test of `AP_MotorsTailsitter` is not written for it.
- The plane and other non-VTOL frames have no VTOL motors and were not swept. `quadplane-can` and `quadplane-PPP` need a CAN or PPP peripheral and were not swept.

### Run history, kept

- `quadplane-motor-sweep-run1-surface-servos-counted/`: my first version counted every output that moved, including control surfaces that move by themselves while the aircraft sits there (servos 1, 2 and 9 appeared in every row). The motor outputs themselves were already the expected ones; the run is kept but not counted.
- `quadplane-motor-sweep-tailsitter-run1-nothing-observed/`: the first tailsitter run looked only at the Motor1..8 functions and the throttle outputs, found nothing and had no expected value; the second version added the tilt functions and the tailsitter test sequence and still found nothing, for the reason above.
- The valid runs: `quadplane-motor-sweep/` (all but the tailsitter) and `quadplane-motor-sweep-tailsitter/`.

## 3. Libraries

Name-matched tests now give simulator evidence for `AP_Soaring` (`Soaring`), `AP_AdvancedFailsafe` (`AdvancedFailsafe`, `AdvancedFailsafeBadBaro`) and `AP_Volz_Protocol` (`Volz`, `VolzMission`), and extra tests for `AP_Parachute` and `AP_Airspeed`; see `coverage/ap-lib-autotest-map.csv`. Name-matched only (test bodies not read).

## Not covered

- Fixed-wing flight quality, TECS or L1 tuning, landing behaviour beyond what the suite asserts, and tailsitter transition behaviour.
- The Mission Planner pages for Plane and QuadPlane (the page's source calls them quad, hexa or octo through the vehicle type; not run).
- The external-simulator frames.
