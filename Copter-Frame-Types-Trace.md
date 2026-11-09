# Copter frame types trace

Scope: what ArduCopter does for each multirotor frame class and type in the supplied snapshot (commit `72b238201f5ea3b556e3809b2ec704fcf701474a`), and what the original Mission Planner 1.3.83 frame page shows and writes for them. Every run is against a disposable ArduCopter SITL in the `Ubuntu-E` WSL distribution. Nothing here is a real aircraft, a real motor or a person using the GUI.

## 1. Motor test across frames (simulator, independent of Mission Planner)

`research-tools/sitl-frame-motor-sweep.py` (run by `research-tools/run-frame-motor-sweep.sh`) starts the SITL binary with `--model <frame>`, reads `FRAME_CLASS` and `FRAME_TYPE` from the vehicle, then sends `MAV_CMD_DO_MOTOR_TEST` for sequence 1..N (10 percent, 1 s each, test order "sequence") on the same MAVLink link while recording `SERVO_OUTPUT_RAW`. A servo counts as moved when its output leaves its idle value by 20 us or more in either direction.

The expected servo for each sequence number comes from the source tree that was built, not from my memory of it:

- Matrix classes (quad, hexa, octa, octa-quad, Y6, deca, dodeca-hexa): the script parses the `testing_order` column of every `MotorDef`/`MotorDefRaw` table in `libraries/AP_Motors/AP_MotorsMatrix.cpp` (and the frame numbers from `AP_Motors_Class.h`). The sequence number n drives the motor whose `testing_order` is n; motor i is on servo output i+1.
- Tri, single and coax: no table, so I transcribed the `_output_test_seq` switch statements of `AP_MotorsTri.cpp` (pitch not reversed), `AP_MotorsSingle.cpp` and `AP_MotorsCoax.cpp` by hand into `HAND_SEQ` in the script. That transcription is the weaker part of the comparison.

Result (`sitl-evidence/frame-motor-sweep/`): 154 of 154 sequences on 23 frames fired exactly the expected servo and no other.

| Frame (SITL --model) | FRAME_CLASS / FRAME_TYPE | Outputs tested | Servo order seen for sequence 1..N | Matches source |
|---|---|---|---|---|
| quad | 1 / 0 | 4 | 3, 1, 4, 2 | 4 of 4 |
| X | 1 / 1 | 4 | 1, 4, 2, 3 | 4 of 4 |
| bfx | 1 / 12 | 4 | 2, 1, 3, 4 | 4 of 4 |
| djix | 1 / 13 | 4 | 1, 4, 3, 2 | 4 of 4 |
| cwx | 1 / 14 | 4 | 1, 2, 3, 4 | 4 of 4 |
| hexa | 2 / 0 | 6 | 1, 4, 6, 2, 3, 5 | 6 of 6 |
| hexax | 2 / 1 | 6 | 5, 1, 4, 6, 2, 3 | 6 of 6 |
| hexa-cwx | 2 / 14 | 6 | 1, 2, 3, 4, 5, 6 | 6 of 6 |
| hexa-dji | 2 / 13 | 6 | 1, 6, 5, 4, 3, 2 | 6 of 6 |
| octa | 3 / 0 | 8 | 1, 3, 8, 4, 2, 6, 7, 5 | 8 of 8 |
| octa-cwx | 3 / 14 | 8 | 1, 2, 3, 4, 5, 6, 7, 8 | 8 of 8 |
| octa-dji | 3 / 13 | 8 | 1, 8, 7, 6, 5, 4, 3, 2 | 8 of 8 |
| octa-quad | 4 / 0 | 8 | 1, 6, 4, 7, 3, 8, 2, 5 | 8 of 8 |
| octa-quad-cwx | 4 / 14 | 8 | 1, 2, 3, 4, 5, 6, 7, 8 | 8 of 8 |
| octa-quad-cor | 4 / 20 | 8 | 1, 6, 4, 7, 3, 8, 2, 5 | 8 of 8 |
| octa-quad-cw-cor | 4 / 21 | 8 | 1, 2, 3, 4, 5, 6, 7, 8 | 8 of 8 |
| deca | 14 / 0 | 10 | 1 to 10 in order | 10 of 10 |
| deca-cwx | 14 / 14 | 10 | 1 to 10 in order | 10 of 10 |
| y6 | 5 / 0 | 6 | 5, 1, 6, 4, 2, 3 | 6 of 6 |
| dodeca-hexa | 12 / 0 | 12 | 1 to 12 in order | 12 of 12 |
| hexadeca-octa | 15 / 0 | 6 | none moved | no table |
| hexadeca-octa-cwx | 15 / 0 | 6 | none moved | no table |
| tri | 7 / 0 | 4 | 1, 4, 7, 2 | 4 of 4 (hand-transcribed) |
| singlecopter | 8 / 1 | 6 | 1, 2, 3, 4, 5, 6 | 6 of 6 (hand-transcribed) |
| coaxcopter | 9 / 1 | 6 | 1, 2, 3, 4, 5, 6 | 6 of 6 (hand-transcribed) |

Reading the table:

- Tri sequence 3 moved servo 7, the tail servo (`AP_MOTORS_CH_TRI_YAW`), and sequence 4 moved servo 2, so the tri "motor sequence" is front right, back motor, tail servo, front left, as the source comment says. Single and coax sequences 1 to 4 are the four flap servos (idle 1500, driven down to 1100 by the 10 percent test) and 5 and 6 the two motors.
- The two hexadeca-octa frames are frame class 15, `MOTOR_FRAME_SCRIPTING_MATRIX`. The motor matrix is created by a Lua script that was not loaded, the idle outputs read 0 and nothing moved. That says nothing about the scripted frame itself; section 9 repeats them with the script installed.
- The 32-motor `dotriaconta_octaquad_x` frame was not run in this first sweep (one `SERVO_OUTPUT_RAW` message holds 16 outputs); section 9 covers it by reading both message instances.
- Frames that are not plain multirotors in the SITL frame list (Gazebo, AirSim, ROS, Scrimmage, CAN, PPP, freestyle and the Callisto model) were not run.

### First run, kept

The first sweep (`sitl-evidence/frame-motor-sweep-run1-upward-detection-only/`) only looked for outputs rising above idle. It matched all 138 matrix sequences, but it missed the tri tail servo and every single and coax flap servo, because those idle at 1500 and the test drives them down to 1100. The script now measures the absolute change and the full list was rerun into `frame-motor-sweep/`. The first run's column names and "n/a (not a matrix frame)" wording differ from the rerun's because the script changed between them.

## 2. Original frame page (`ConfigFrameClassType`) against frames

`research-tools/PageFrameProbe.cs` (run by `research-tools/run-frame-page-probe.ps1`) builds the original page from the data-redirected `MissionPlanner.exe`, calls `Activate()`, reads which radio buttons are checked and enabled, and reads `FRAME_CLASS` and `FRAME_TYPE` back from the vehicle (`comPort.GetParam`). A harness drives the page; no person clicked. Evidence in `sitl-evidence/frame-page/`.

What the page shows after `Activate()`, per simulator frame:

| Simulator frame | Vehicle class / type | Class radio checked | Type radio checked | Type radios enabled |
|---|---|---|---|---|
| quad plus | 1 / 0 | Quad | Plus | Plus, X, V, H, V-tail |
| quad X | 1 / 1 | Quad | X | Plus, X, V, H, V-tail |
| hexa | 2 / 0 | Hexa | Plus | Plus, X |
| octa | 3 / 0 | Octa | Plus | Plus, X, V, H |
| octa-quad | 4 / 0 | Octa-quad | Plus | Plus, X, V, H |
| y6 | 5 / 0 | Y6 | Plus | X, Y6 |
| tri | 7 / 0 | Tri | Plus | none (type group disabled) |
| heli | 6 / 1 | Heli | X | none (type group disabled) |
| deca | 14 / 0 | none | Plus | none (type group disabled) |
| single copter | 8 / 1 | none | X | none (type group disabled) |

Findings:

- The page has class buttons for undefined, quad, hexa, octa, octa-quad, Y6, heli and tri only. Deca, dodeca-hexa, single, coax, tailsitter, the dual and quad helicopters and the scripting matrices have no button. For a deca or single copter vehicle the probe saw no class radio checked and the type group disabled; I did not look at the pictures the page draws. The type buttons are plus, X, V, H, Y6B and V-tail only; the Betaflight, DJI and clockwise X orderings (types 12, 13, 14), `I`, the co-rotating X8 types and the others have no button. Observed with `research-tools/run-frame-page-probe-extra.ps1` (`sitl-evidence/frame-page/state-quad-bfx.txt` and the others): for quad Betaflight X (12), DJI X (13) and clockwise X (14), hexa DJI X and octa clockwise X, the page checks the right class button, checks no type button, leaves the usual type buttons enabled for the class, and the vehicle's `FRAME_TYPE` is unchanged after `Activate()`. A user is shown a frame class with no type selected, with no hint that the type is one the page cannot display.
- For hexa the page enables Plus and X, and for Y6 it enables X and Y6B (the "Y" radio). The Y6 "plus" type (0) is the vehicle's, but no Plus button is enabled, so the checked Plus button for Y6 shows the vehicle's type on a disabled control.
- Changing the class through the page: with a quad plus vehicle, checking the Hexa radio changed the vehicle's `FRAME_CLASS` 1 to 2 immediately (type left at 0), and then checking the X radio changed `FRAME_TYPE` 0 to 1. Both read back from the vehicle. No message box appeared.
- The simulator was then restarted without wiping its stored parameters and motor-tested (`sitl-evidence/frame-page/restart-sweep/`): it came up as class 2, type 1 (hexa X) and all six sequences matched the hexa X table (servo order 5, 1, 4, 6, 2, 3), the same order the `hexax` frame gave in the sweep. So a class and type chosen on the page do take effect after the restart. The restart was a process restart of the simulator with its `eeprom.bin` kept, not a `MAV_CMD_PREFLIGHT_REBOOT`.
- In every state run the vehicle's class and type after `Activate()` equal the values before it. From the source, `Activate()` calls `DoClass` and `DoType`, which write both parameters back; the probe shows the values were unchanged, not whether a write was sent.

## 3. Mission Planner's other frame page

`ConfigFrameType` (the older page) stays disabled when `FRAME` is absent, as recorded in `Setup-Page-State-Trace.md`; this run did not exercise it.

## 4. What the motor test page labels, from `APMotorLayout.json` (static comparison)

The original `ConfigMotorTest` page (`GCSViews/ConfigurationView/ConfigMotorTest.cs`) builds one "Test motor A, B, C..." button per motor. It gets the motor count and the label "Motor Number: n, CW/CCW" next to button k from `APMotorLayout.json` (header "AP_Motors library test ver 1.2", shipped next to `MissionPlanner.exe`), looking up the vehicle's `FRAME_CLASS` and `FRAME_TYPE`; the motor shown next to button k is the one whose `TestOrder` is k, and every button sends `MAV_CMD_DO_MOTOR_TEST` with that sequence number k. If the pair is not in the file the page falls back to a guess from the MAVLink vehicle type (tri 4, quad 4, hexa 6, octa 8, dodeca 12, helicopter 0, anything else 8).

`research-tools/compare-mp-motor-layout.py` compares the JSON with the tables in the supplied `AP_MotorsMatrix.cpp` (`sitl-evidence/motor-layout-compare/`):

- 56 of 56 combinations present in both agree on the motor count, on which motor number has which test order, and on CW/CCW. These are the quad, hexa, octa, octa-quad, Y6, dodeca-hexa and deca entries in the file.
- 19 entries in the JSON (all of class 7, tri) have no matrix table because `AP_MotorsTri` is a separate class. All 19 match the test sequence I transcribed by hand from `AP_MotorsTri::_output_test_seq` (outputs 1, 4, 7, 2; or 4, 7, 1, 2 for type 6 "pitch reversed"). The simulator's tri run in section 1 gave 1, 4, 7, 2.
- 3 combinations exist in the source but not in the JSON: quad type 19 (Y4) and octa-quad types 20 and 21 (co-rotating X8). For these the page would use the vehicle-type guess: 4 buttons for Y4 and 8 for the octa-quad ones, matching the real motor counts, but with no "Motor Number" labels. Observed in section 6.
- The JSON has no entries for deca types other than 0, 1 and 14, no helicopter, single, coax or scripting classes. From the source, a coax or single copter would get the default eight buttons although the vehicle has six test sequences, and a helicopter gets none. Not observed in the page.

So the labels the page shows for the layouts it knows are consistent with the firmware's tables. Static comparison only: the page itself was not run against these frames.

Parser notes (kept because they changed results): my first version of the comparison reported 4 differences (quad V, V-tail, A-tail, octa-quad V) that were parser mistakes: V frames use numeric yaw factors, and V-tail/A-tail are written with `add_motor(...)` calls rather than a table, so a stale label list gave them the PLUSREV table. After fixing the parser there are no differences. `sitl-frame-motor-sweep.py` has the same stale-label weakness for V-tail and A-tail, but none of the frames I swept use those types, so the swept results are not affected.

## 5. Helicopter frames: ArduPilot's own `Helicopter` autotest suite

The `Helicopter` suite (build target `arducopter-heli`, 37 tests: 12 common and 25 helicopter-specific) was run against the pinned snapshot copy in WSL with `research-tools/run-autotest.sh`, speedup 10, on disposable simulators. Evidence: `sitl-evidence/autotest-helicopter/` (gzipped logs and `autotest-results.csv`).

Result of the complete run (`Helicopter-rerun2.log.gz`): 36 passed, 1 failed (`RotorRunup`).

- Passed, among others: `AVCMission`, `PosHoldTakeOff`, `StabilizeTakeOff`, `SplineWaypoint`, `AutorotationPreArm`, `Autorotation`, `ManAutorotation`, `governortest`, `GovernorNotEngagedManualThrottle`, `TurbineStart`, `TurbineCoolDown`, `NastyMission`, `PIDNotches`, `AutoTune`, `DDFPTail`, `DDVPTail`, `HeliQuad`, `HeliQuadFlip`, `HeliQuadInvertedFlight`, `HeliSingleInvertedFlight`, `MountFailsafeAction`, `StickArmingRequiresZeroThrottle`.
- `FlyEachFrame` passed: for each of the seven internal helicopter frames (heli, heli-blade360, heli-ddfptail, heli-ddvptail, heli-dual, heli-gas, heli-quad) it restarts the simulator with that model, takes off to 10 m and does an RTL. That is flight of every internal helicopter frame in the simulator, by the vehicle's own test, not a test of mixing quality.
- The autorotation tests pass. They fly in POSHOLD and other modes with the helicopter parameters; I did not establish that any of them enters flight mode 26 (AUTOROTATE) itself, so the earlier "mode 26 not entered" observation in the mode ledger stays open.
- Not covered by this suite: the motor test page and `DO_MOTOR_TEST` for helicopters (the page reports 0 motors for a helicopter, from its source).

### `RotorRunup` failure (explained: a 1 s wall-clock wait against an 11 s simulator-time runup)

- It failed every time: in the full suite, alone at speedup 10 (6.7 s), alone at speedup 1 (41 s), and alone at speedups 50 and 100 (`Helicopter-rotorrunup-speed50/100.log.gz`). The logs and progress files are in the evidence folder.
- The exception comes from the second `assert_receive_message("SERVO_OUTPUT_RAW", condition=servo1_raw > armed value + 50)` in `helicopter.py` (`RotorRunup`), which uses the harness default timeout of 1 s of **wall-clock** time. The first `SERVO_OUTPUT_RAW` wait, right after arming, succeeds. The test sets `H_RSC_RUNUP_TIME` to 10 s, raises RC8 and RC3, and then waits for the collective servo to pass the threshold.
- Ruled out: the message stream. A helicopter simulator and a quad simulator both deliver `SERVO_OUTPUT_RAW` at about 10 Hz, disarmed and armed (`sitl-evidence/heli-servo-rate/heli.json`, `quad.json`).
- Ruled out: asking for more simulator speed. At speedup 50 and 100 the failure is the same, because on this machine the simulator does not run faster than about ten times real time: the harness's own "Took 35 seconds to become armable" (simulator time) took about 4 s of wall time at speedup 100.
- Confirmed by changing the test: with the one wait widened from 1 s to 60 s (a temporary edit of the pinned snapshot copy, diff in `sitl-evidence/heli-servo-rate/rotor-runup-timeout-patch.diff`, file restored byte for byte afterwards) the test **passes** (`Helicopter-rotorrunup-patched-timeout60.log.gz`). It prints "Runup time 11" (simulator seconds) and the collective reaches 1525 us 1.1 s of wall time after the wait starts, which is just over the 1 s limit. The same wait fails at 1.03 s in the unpatched runs.
- Conclusion: this is a timing margin in the autotest on this machine (a 10 s runup is about 1.1 s of wall time at the speed the simulator manages here), not evidence of a helicopter firmware fault. On a machine that really runs the simulator at several times that speed the test would pass unpatched; I did not have such a machine. Attempts to replicate the timing with plain pymavlink (STABILIZE forced arm: collective followed the stick in 0.16 s; LOITER normal arm: did not arm in 150 s) were unsuccessful and are kept (`rotor-runup-timing-run1-stabilize.json`, `run2-loiter-did-not-arm.json`).

### Run history, kept

The first helicopter run (`Helicopter-killed-partial.log.gz`, 15 passed, 1 failed `RotorRunup`) ended when the SSD was unplugged and the tool call that held it hit its time limit. A second start overwrote the log of the first rerun by mistake (`Helicopter-rerun1-clobbered.log.gz`, unusable), and both were killed. The complete run is `Helicopter-rerun2` above, started detached from the tool call.

## 6. The motor test page against frames (original page, simulator)

`research-tools/PageMotorLayoutProbe.cs` (run by `research-tools/run-motor-layout-probe.ps1`) builds the original `ConfigMotorTest` page against 14 simulator frames, calls `Activate()` and lists every button and label the page drew, without pressing any button. `research-tools/compare-page-labels-with-sweep.py` lines the "Motor Number" labels up with the servo outputs that moved for the same sequence number in the section 1 sweep. Evidence: `sitl-evidence/motor-layout-page/` (`layout-<frame>.txt`, `page-vs-sweep.csv`). A harness drove the page; no person used it.

| Frame | Page text | Buttons drawn | Result |
|---|---|---|---|
| quad plus, X, Betaflight X | Quad / Plus, X, BetaFlightX | 4 | motor numbers in button order equal the servos that moved (3 1 4 2; 1 4 2 3; 2 1 3 4) |
| hexa plus, hexa X | Hexa / Plus, X | 6 | equal (1 4 6 2 3 5; 5 1 4 6 2 3) |
| octa | Octa / Plus | 8 | equal (1 3 8 4 2 6 7 5) |
| octa-quad | OctaQuad / Plus | 8 | equal (1 6 4 7 3 8 2 5) |
| Y6 | Y6 / Plus | 6 | equal (5 1 6 4 2 3) |
| tri | Tri / Plus | 4 | equal (1 4 7 2); the labels carry no CW/CCW text |
| deca | "Class: unknown", "Type: unknown" | 10 | equal (1 to 10), but the class and type text could not be resolved |
| dodeca-hexa | DodecaHexa / Plus | 12 | equal (1 to 12) |
| single copter | SingleCopter / X | 8 | no "Motor Number" labels; the vehicle has six test sequences |
| coax copter | CoaxCopter / X | 8 | no labels; the vehicle has six test sequences |
| helicopter | Heli / X | 0 | no motor buttons (motor count 0) |

So for every frame in the page's layout file, button k tests the motor the label next to it names, and that is the servo output that moved when the simulator was told to test sequence k. That was seen on all eleven matrix and tri frames above, with the CW/CCW text coming from the file (section 4 compares it with the source).

Findings that differ from what a user would expect:

- Single and coax copters get eight buttons although the vehicle has six test sequences (four flap servos and two motors, section 1), and no labels. The seventh and eighth buttons send sequence numbers 7 and 8; from the source (`_output_test_seq` has no case for them) they should do nothing; section 8 presses them and confirms it.
- The "Test all motors" button on those frames sends eight single-motor commands, and "Test all in sequence" sends a motor count of eight. Section 8 observed it: six of the eight act.
- A deca vehicle shows "Class: unknown" and "Type: unknown": the page's parameter metadata has no names for class 14. The buttons and labels are right because `APMotorLayout.json` has deca entries.
- A helicopter gets no motor buttons at all, from `motormax = 0`.
- This confirms the source reading in section 4 that the page's behaviour for Y4 and the co-rotating octa-quad types would rely on its vehicle-type guess; those frames are not in the simulator frame list and were not probed.

### Frame types that are missing from the layout file, observed

Section 4 predicted from the source that quad Y4 (type 19) and octa-quad X_COR and CW_X_COR (types 20 and 21) would get the page's vehicle-type guess. `research-tools/run-motor-layout-extra.ps1` set each by parameter on a simulator (`research-tools/prepare-frame-type.sh`, a restart that keeps the stored parameters), and the original page was built against it (`sitl-evidence/motor-layout-page/extra-*.txt`, nothing pressed):

| Vehicle | Page text | Buttons drawn | "Motor Number" labels |
|---|---|---|---|
| quad, `FRAME_TYPE=19` (Y4) | Quad / Y4 | 4 | none |
| octa-quad, `FRAME_TYPE=20` (X_COR) | OctaQuad / "unknown" | 8 | none |
| octa-quad, `FRAME_TYPE=21` (CW_X_COR) | OctaQuad / "unknown" | 8 | none |

So the prediction held: the button counts are right (4 and 8, matching the motors in section 1), but there are no labels telling the user which motor number each button drives, and the two octa-quad types are shown as "unknown".

## 7. Flight of every internal Copter frame (ArduPilot's own `FlyEachFrame`, earlier Copter run)

The Copter suite passed `FlyEachFrame` in the complete Copter autotest run recorded earlier (`sitl-evidence/autotest/Copter.log.gz`, `autotest-final.csv`: PASSED). For each frame in the simulator's frame list that is not external or marked broken, the test restarts the simulator with that model (installing the frame's example Lua script and enabling scripting for the scripted ones), takes off to 10 m with a hook that fails the test if the yaw rate exceeds 20 degrees per second, hovers, switches to ALT_HOLD, and five times applies 0.5 s of yaw stick and waits 5 s with a hook on roll and pitch, then does an RTL. `research-tools/build-fly-each-frame-table.py` extracts the per-frame outcome from the log into `coverage/copter-fly-each-frame.csv`: 44 frames listed, 31 flown, 13 skipped by the test itself.

- Flown (31): quad, plus ("+"), X, Betaflight X, DJI X, clockwise X, the hexa variants (hexa, hexa-cwx, hexa-dji, hexax), the octa variants (octa, octa-cwx, octa-dji), the octa-quad variants (octa-quad, -cwx, -cor, -cw-cor), deca and deca-cwx, Y6, dodeca-hexa, tri, single copter, coax copter, the Callisto and freestyle models, the PPP and periph-compass variants, and the scripted-matrix frames dotriaconta-octaquad-x, hexadeca-octa and hexadeca-octa-cwx (these use their example Lua scripts, so they are flown in the simulator even though the motor sweep in section 1 could not test them without a script).
- Skipped by the test (13): IrisRos, airsim-copter, calibration, gazebo-iris and scrimmage-copter (external simulators); the seven helicopter frames (the Copter suite says they need a different binary; the Helicopter suite in section 5 flew them); quad-can (needs a CAN peripheral).

So every internal Copter and helicopter frame has been flown at least once in the simulator by the vehicle's own tests, and the motor output mapping of 23 of them has been checked directly (section 1).

What this test would not catch (read from the source, not a defect I measured): the roll and pitch hook compares `m.pitch` and `m.roll` against +2 degrees without taking an absolute value, so a negative excursion of any size passes; the test does not look at motor saturation, tracking error or attitude oscillation; one takeoff per frame, no wind, no failures.

## 8. Pressing the extra motor buttons on single and coax (original page, simulator)

Section 6 found that the page draws eight "Test motor" buttons for the single and coax copter frames although the vehicle has six test sequences. `research-tools/PageMotorButtonsProbe.cs` (run by `research-tools/run-motor-buttons-probe.ps1`) built the original page against each frame, set 10 percent for 2 s, and invoked the page's own button handler for buttons E, F, G and H (motor tags 5 to 8), then "Test all motors" and "Stop all motors", while `sitl-servo-observer.py` recorded `SERVO_OUTPUT_RAW` on a second MAVLink port (`research-tools/analyze-motor-buttons.py` lines up the times). A harness pressed the buttons, not a person. Evidence: `sitl-evidence/motor-buttons/`.

| Page action | Single copter | Coax copter |
|---|---|---|
| Test motor E (tag 5) | servo 5 rose 100 us | servo 5 rose 100 us |
| Test motor F (tag 6) | servo 6 rose 100 us | servo 6 rose 100 us |
| Test motor G (tag 7) | nothing moved | nothing moved |
| Test motor H (tag 8) | nothing moved | nothing moved |
| Test all motors | servos 1 to 4 moved 400 us (down from 1500 to 1100), servos 5 and 6 rose 100 us | same |
| Stop all motors | nothing moved | nothing moved |

No message box appeared for any action, so the page does not tell the user that buttons G and H do nothing: the vehicle accepts the command for sequence 7 and 8 and does not move any output, as the source (`_output_test_seq` has no case for them) predicted. "Test all motors" sends eight single-motor commands, of which six act. On these frames the first four sequences are flap servos, so a 10 percent "motor" test drives them 400 us from their centre position; the page labels all of them "Test motor <letter>".

## 9. Scripted motor matrices (frame class 15) and the Y4 type

Section 1 could not test the scripted-matrix frames because the matrix is created by a Lua script that was not loaded. `research-tools/sitl-frame-motor-sweep.py` now handles them: on a first start it sets `SCR_ENABLE=1` (a frame spec such as `quad:FRAME_TYPE=19` also sets the listed parameters), stops the simulator, copies the frame's example script (`libraries/AP_Scripting/examples/MotorMatrix_*.lua`, as named by `frame_example_script` in `vehicleinfo.json`) into `<work>/scripts`, restarts without wiping the parameters, and then sends the motor test as before. The expected order comes from the `add_motor(...)` lines of the script (for the 32-motor script, whose motors are added in a loop, by applying the loop body by hand: bank b has testing orders 4b+1, 4b+3, 4b+4, 4b+2). It reads both `SERVO_OUTPUT_RAW` instances, so outputs 17 to 32 are observed.

| Frame | Outputs tested | Sequences matching the script | Evidence folder |
|---|---|---|---|
| quad with `FRAME_TYPE=19` (Y4) | 4 | 4 of 4 (matrix table, not a script) | `frame-motor-sweep-scripted-and-y4/` |
| hexadeca-octa (class 15) | 16 | 16 of 16 | `frame-motor-sweep-scripted-and-y4/` |
| hexadeca-octa-cwx (class 15) | 16 | 16 of 16 | `frame-motor-sweep-scripted-rerun/` |
| dotriaconta-octaquad-x (class 15, 32 motors) | 32 | 32 of 32 | `frame-motor-sweep-scripted-rerun2/` |

Run history, kept: in the first run the cwx and 32-motor frames were not compared (my Lua parser rejected angles such as 22.5 and the loop in the 32-motor script, so the folders for the first run show "expected_known False" for them); the parser was fixed and each of the two was rerun in its own folder. The hexadeca-octa and Y4 results come from the first run unchanged.

With this, the output mapping has been checked directly for 27 frames: the 23 of section 1, the three scripted frames and Y4. The scripted tests prove that the example scripts create a matrix whose motor test sequence matches the script's own testing orders; they do not check the script's mixing factors.

## 10. The real Mission Planner window driven by a script (simulator)

The computer-use tool could not be granted the research copy (account in `sitl-evidence/live-gui-attempt/NOTES.md`), so I drove the real window of the research copy of Mission Planner 1.3.83 (the data-redirected copy used for all probes, running as its own process beside a disposable Copter simulator) with window messages sent only to that process's windows: `research-tools/gui-driver.ps1` (capture with `PrintWindow`, child-window list, posted mouse messages, combo selection, `BM_CLICK`). A script pressed the buttons, not a person, and the window is the research copy, not an unmodified installation; screenshots of every step are in `sitl-evidence/live-gui-driven/` (`00-start.png` to `10-after-*.png`).

What the real GUI did:

1. The connection box offers a TCP entry. Selecting it and pressing CONNECT opened Mission Planner's own "remote host" and "remote Port" dialogs, with `127.0.0.1` and `5760` already filled in; pressing OK on both connected: the title bar became "ArduCopter V4.8.0-dev (15a10bb4)" and the connect button became DISCONNECT.
2. SETUP shows the left menu (Install Firmware, Mandatory Hardware, Optional Hardware, Advanced). Mandatory Hardware lists Frame Type, Accel Calibration, Compass, Radio Calibration, Servo Output, Serial Ports, ESC Calibration, Flight Modes, FailSafe, Initial Tune Parameters, HW ID, ADSB. Optional Hardware lists RTK/GPS Inject, CubeID Update, Sik Radio, CAN GPS Order, Battery Monitor (and 2), DroneCAN/UAVCAN, Joystick, Compass/Motor Calibration, Range Finder, Airspeed, PX4Flow, Optical Flow, OSD, Camera Gimbal, Motor Test, Bluetooth Setup, Parachute, ESP8266 Setup, Antenna Tracker, FFT Setup. (These menu entries are listed even where the page behind them is disabled for this firmware, as found in `Setup-Page-Disabled-Reasons-Trace.md`; I did not open those.)
3. The Frame Type page showed the eight class pictures with Quad highlighted and "Plus" selected, plus an "Other" radio button next to the V-tail option that my earlier harness probe and the source I read had not listed. The harness found Quad and Plus checked as well.
4. The Motor Test page showed "Class: Quad", "Type: Plus", buttons A to D labelled "Motor Number: 3, CW", "1, CCW", "4, CW", "2, CCW", plus Test all, Stop all and Test all in Sequence, with throttle 5 percent and duration 2 s. These are the same labels the harness produced (`Copter-Frame-Types-Trace.md` section 6).
5. Pressing buttons with `BM_CLICK` while an independent observer on SERIAL1 recorded `SERVO_OUTPUT_RAW` (`gui-motor-test-summary.csv`): Test motor A raised servo output 3, Test motor B raised servo output 1, each by 50 us (5 percent of 1000 to 2000 us); Test all in Sequence raised the outputs in the order 3, 1, 4, 2 at about 0, 3, 6 and 9 s (`gui-sequence-order.txt`); Stop all moved nothing. No message box appeared. The order and the A and B results match the sweep and the harness for the plus quad.

What this adds and what it does not: the live window of the research copy, connecting over TCP and showing the frame and motor test pages with the right data, and its buttons driving the right outputs, was observed for one frame (plus quad) on one run. It is script-driven, not a person; nothing about the pages in the list above that I did not open; nothing for other frames, other vehicles or other pages in the live window; and the copy is data-redirected, so I do not count it as the original unmodified GUI.

Failed attempts, kept: UI Automation exposes only plain panes for this window (`sitl-evidence/live-gui-uia/uia-tree.txt`); a first run clicked window coordinates that resolved to a container (`live-gui-driven-run1-clicks-missed/`); a second run clicked the buttons by handle with posted mouse messages, which the buttons did not act on (`live-gui-driven-run2-mouse-messages-no-effect/`; the same method did work for the dialog buttons and the toolbar); the third, with `BM_CLICK`, worked.

## 11. All 33 Mandatory and Optional Hardware pages in the live window (simulator)

`research-tools/run-live-gui-pages.ps1` repeated the section 10 setup (research copy, TCP to a disposable Copter simulator, window messages), opened every entry of the SETUP menu's Mandatory Hardware (12) and Optional Hardware (21) groups one after another, waited 3 s on each, dismissed any dialog the page opened (OK, else No, else Cancel; the dialog title and texts were recorded first), and saved a screenshot, the list of visible child windows with their text and enabled state, and counts (`sitl-evidence/live-gui-pages/`: `pages-summary.csv`, `NNN-<page>.jpg`, `NNN-<page>-controls.txt`). Not opened: Install Firmware (it flashes firmware) and the Advanced group. A script did this, not a person; the counts are of Windows child windows, so a page's own drawn content (pictures, graphs) is not in them, and every page includes about 50 child windows for the left menu itself, with about 4 of them reported disabled on every page.

| Page | Dialog the page opened | Visible child windows | Buttons | Edits | Combos | Disabled |
|---|---|---:|---:|---:|---:|---:|
| Frame Type | none | 84 | 15 | 3 | 3 | 5 |
| Accel Calibration | none | 62 | 3 | 3 | 3 | 4 |
| Compass | none | 84 | 10 | 4 | 4 | 6 |
| Radio Calibration | none | 74 | 4 | 3 | 3 | 4 |
| Servo Output | none | 270 | 16 | 51 | 19 | 4 |
| Serial Ports | none | 94 | 7 | 3 | 17 | 4 |
| ESC Calibration | none | 86 | 2 | 8 | 4 | 4 |
| Flight Modes | none | 90 | 13 | 3 | 9 | 6 |
| FailSafe | [FailSafe] Ensure your props are not on the Plane/Quad | 125 | 1 | 7 | 5 | 4 |
| Initial Tune Parameters | none | 71 | 3 | 9 | 4 | 4 |
| HW ID | none | 54 | 0 | 3 | 3 | 4 |
| ADSB | none | 74 | 5 | 7 | 5 | 11 |
| RTK-GPS Inject | none | 83 | 4 | 3 | 5 | 4 |
| CubeID Update | none | 64 | 4 | 4 | 4 | 5 |
| Sik Radio | none | 202 | 32 | 15 | 37 | 67 |
| CAN GPS Order | none | 57 | 0 | 3 | 3 | 4 |
| Battery Monitor | none | 79 | 1 | 12 | 6 | 5 |
| Battery Monitor 2 | none | 77 | 1 | 10 | 6 | 6 |
| DroneCAN-UAVCAN | none | 83 | 6 | 15 | 4 | 4 |
| Joystick | none | 193 | 36 | 36 | 20 | 4 |
| Compass-Motor Calibration | none | 57 | 1 | 4 | 3 | 4 |
| Range Finder | none | 61 | 0 | 3 | 4 | 5 |
| Airspeed | none | 61 | 1 | 3 | 5 | 6 |
| PX4Flow | none | 58 | 1 | 3 | 3 | 4 |
| Optical Flow | none | 88 | 0 | 9 | 4 | 22 |
| OSD | none | 58 | 1 | 3 | 3 | 4 |
| Camera Gimbal | none | 187 | 5 | 26 | 11 | 139 |
| Motor Test | none | 81 | 9 | 5 | 3 | 4 |
| Bluetooth Setup | none | 64 | 1 | 6 | 4 | 4 |
| Parachute | none | 73 | 1 | 6 | 5 | 14 |
| ESP8266 Setup | none | 77 | 3 | 10 | 5 | 29 |
| Antenna Tracker | none | 92 | 3 | 14 | 6 | 4 |
| FFT Setup | none | 96 | 24 | 4 | 3 | 4 |

What this shows:

- All 33 entries opened in the live window without crashing the application or leaving the connection; the only dialog any page raised was the one on the FailSafe page ("Ensure your props are not on the Plane/Quad"), which the sweep dismissed with OK.
- Pages that show only the menu plus a title or a line of text (about 54 to 58 child windows in total, no buttons): HW ID, CAN GPS Order (shows "UAVCAN GPS Order / Set the GPS order if required" and nothing else), Compass-Motor Calibration, PX4Flow, OSD, Range Finder. For CAN GPS Order this is the page that raised a null reference in the harness (`Setup-Page-Disabled-Reasons-Trace.md`); in the live window no dialog appeared and the page shows only its header, which fits an `Activate()` that stopped part way with the error not shown, but I did not show that.
- Camera Gimbal shows a full page (187 child windows) of which 139 are disabled, which fits `ConfigMount` being disabled because `CAM_TRIGG_TYPE` does not exist on this firmware (`Setup-Page-Disabled-Reasons-Trace.md`); ESP8266 Setup (29 disabled of 77), Parachute (14 of 73), Optical Flow (22 of 88) and Sik Radio (67 of 202) also have many disabled controls without a cause shown here.
- The menu lists CAN GPS Order, Camera Gimbal, ESP8266 Setup and Antenna Tracker as normal entries even though the page behind some of them is disabled or empty for this vehicle: the menu does not reflect the firmware.
- The Frame Type and Motor Test pages here are the ones section 10 covers in more detail; Frame Type shows 15 buttons, 3 edit boxes and 3 combo boxes as windows next to the picture controls.

Not covered: the Advanced group, Install Firmware, pressing any control on these pages other than the motor test buttons in section 10, other frames or vehicles in the live window, and a person using any of them.

## 12. Changing the frame in the live window (simulator)

`research-tools/run-live-gui-frame-change.ps1` repeated the section 10 setup, opened SETUP > Mandatory Hardware > Frame Type in the real window of the research copy, pressed the Hexa class picture and then the "X, Y6A" type radio button (both with `BM_CLICK` on the child window under the picture or radio), and after each step read `FRAME_CLASS` and `FRAME_TYPE` from the vehicle on SERIAL1 with an independent pymavlink client (`sitl-evidence/live-gui-frame-change/vehicle-frame-readings.txt`):

| Step | FRAME_CLASS | FRAME_TYPE |
|---|---:|---:|
| Before any GUI action (plus quad) | 1 | 0 |
| After pressing the Hexa class picture | 2 | 0 |
| After pressing the "X" type radio | 2 | 1 |

The screenshot after the last step (`03-after-x.png`) shows the Hexa picture highlighted, the X radio selected and the X pictures bright. No dialog appeared at any step. This is the same result as the harness-driven change in section 2 (quad plus to hexa to X), now through the live window; it was run once, by a script, on the data-redirected research copy. As in section 2, the new frame takes effect in the vehicle only after a restart; I did not restart this simulator after the change.

## 13. The live window against eight simulators (Copter frames, Sub, Rover, QuadPlane)

`research-tools/run-live-gui-vehicles.ps1` did the section 10 connection for eight disposable simulators one after another (a fresh simulator and a fresh Mission Planner process each time), opened SETUP, expanded Optional Hardware, opened Motor Test and recorded the page; on the four multi-motor Copter frames it also pressed "Test all in Sequence" with `BM_CLICK` while an independent observer recorded `SERVO_OUTPUT_RAW` and compared the order of first movement with the sweep (`research-tools/analyze-gui-sequence-generic.py`). Evidence: `sitl-evidence/live-gui-vehicles/` (`vehicles-summary.csv`, screenshots and control lists per simulator). A script drove the real window of the research copy; not a person.

| Simulator | Window title shows | Motor Test page | Buttons | Sequence press: servo order in the live window | Sweep order | Same |
|---|---|---|---:|---|---|---|
| Copter hexa | ArduCopter V4.8.0-dev | Class Hexa, Type Plus; labels 1 CW, 4 CCW, 6 CW, 2 CCW, 3 CW, 5 CCW | 6 | 1 4 6 2 3 5 | 1 4 6 2 3 5 | yes |
| Copter octa | ArduCopter | Class Octa, Type Plus; 8 labels | 8 | 1 3 8 4 2 6 7 5 | 1 3 8 4 2 6 7 5 | yes |
| Copter Y6 | ArduCopter | Class Y6, Type Plus; 6 labels | 6 | 5 1 6 4 2 3 | 5 1 6 4 2 3 | yes |
| Copter tri | ArduCopter | Class Tri, Type Plus; labels 1, 4, 7, 2 (no CW/CCW) | 4 | 1 4 7 2 | 1 4 7 2 | yes |
| Copter single | ArduCopter | Class SingleCopter, Type X; no motor labels | 8 | not pressed | | |
| Sub vectored | no vehicle name after "on" | Class and Type "unknown"; no labels; **all 8 buttons disabled** | 8 | not pressed | | |
| Rover | ArduRover | Class and Type "unknown"; no labels | 4 | not pressed | | |
| QuadPlane | ArduPlane | Class Quad, Type X; labels 1 CCW, 4 CW, 2 CCW, 3 CW | 4 | not pressed | | |

What this shows: in the real window the four Copter frames' pages carry the same labels as the harness and the firmware tables, and the live sequence press moved the outputs in the same order as the sweep on all four. The Sub page is present in the menu but all eight of its buttons are disabled, as the harness found; the live window's title bar does not name the ArduSub vehicle (only "on" follows the version), which I did not investigate. Rover and the QuadPlane show what the harness showed. No dialog appeared on any page. One run per simulator, script-driven, data-redirected copy; the single copter, Sub, Rover and QuadPlane buttons were not pressed here.

Failed attempt, kept: the first run (`sitl-evidence/live-gui-vehicles-run1-menu-text-not-matched/`) connected to all eight but found no Motor Test entry because my script matched the menu text exactly and the entries carry leading spaces ("      Motor Test"); the control lists and screenshots in that folder show the entry present.

## Not covered

- A person using the frame page or motor test page (section 10 is a script driving the real window of the research copy, for one frame), other frames in the live window, and the picture drawn for each frame.
- The motor test page's per-motor buttons on frames other than the plus quad, single and coax (section 8 pressed buttons only on single and coax; the sweep in section 1 bypasses the page).
- Flying any of these frames. The motor test checks the output mapping, not mixing, yaw direction, motor direction (`SERVO_BLH_RVMASK` and similar) or flight behaviour. I did not check which autotests set a frame other than quad plus.
- Scripting matrix frames (class 15 to 17) and the 32-motor frame.
- Helicopter frames in the motor test page and in the frame-class page's pictures (the page probe only read the helicopter state); `RotorRunup` is explained in section 5 (timing margin of the test).
