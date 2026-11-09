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
- The two hexadeca-octa frames are frame class 15, `MOTOR_FRAME_SCRIPTING_MATRIX`. The motor matrix is created by a Lua script that was not loaded, the idle outputs read 0 and nothing moved. That says nothing about the scripted frame itself.
- The 32-motor `dotriaconta_octaquad_x` frame was not run: one `SERVO_OUTPUT_RAW` message holds 16 outputs.
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

- The page has class buttons for undefined, quad, hexa, octa, octa-quad, Y6, heli and tri only. Deca, dodeca-hexa, single, coax, tailsitter, the dual and quad helicopters and the scripting matrices have no button. For a deca or single copter vehicle the probe saw no class radio checked and the type group disabled; I did not look at the pictures the page draws. The type buttons are plus, X, V, H, Y6B and V-tail only; the Betaflight, DJI and clockwise X orderings (types 12, 13, 14), `I`, the co-rotating X8 types and the others have no button. I did not run the page against a frame with one of those types; for quad `bfx`, `djix` and `cwx` I expect no type button to be checked, from the source, but that is not observed.
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
- 3 combinations exist in the source but not in the JSON: quad type 19 (Y4) and octa-quad types 20 and 21 (co-rotating X8). For these the page would use the vehicle-type guess: 4 buttons for Y4 and 8 for the octa-quad ones, matching the real motor counts, but with no "Motor Number" labels. This is read from the source, not observed.
- The JSON has no entries for deca types other than 0, 1 and 14, no helicopter, single, coax or scripting classes. From the source, a coax or single copter would get the default eight buttons although the vehicle has six test sequences, and a helicopter gets none. Not observed in the page.

So the labels the page shows for the layouts it knows are consistent with the firmware's tables. Static comparison only: the page itself was not run against these frames.

Parser notes (kept because they changed results): my first version of the comparison reported 4 differences (quad V, V-tail, A-tail, octa-quad V) that were parser mistakes: V frames use numeric yaw factors, and V-tail/A-tail are written with `add_motor(...)` calls rather than a table, so a stale label list gave them the PLUSREV table. After fixing the parser there are no differences. `sitl-frame-motor-sweep.py` has the same stale-label weakness for V-tail and A-tail, but none of the frames I swept use those types, so the swept results are not affected.

## Not covered

- A person using the frame page or motor test page, and the picture drawn for each frame.
- The motor test page's per-motor buttons on non-quad frames (the page probe for motor test used only the plus quad frame; the sweep above bypasses the page).
- Flying any of these frames. The motor test checks the output mapping, not mixing, yaw direction, motor direction (`SERVO_BLH_RVMASK` and similar) or flight behaviour. I did not check which autotests set a frame other than quad plus.
- Scripting matrix frames (class 15 to 17) and the 32-motor frame.
- The helicopter classes: see the helicopter section below if it has been added.
