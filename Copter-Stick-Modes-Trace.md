# Copter stick-response trace

Scope: ArduCopter flight modes that have **no test named for them** in ArduPilot's own Copter autotest (Sport, Acro, Drift, GuidedNoGPS, SystemID), plus Stabilize and AltHold as an angle reference. Disposable source-built Copter SITL (non-debug build from the pinned snapshot copy), pymavlink, one simulated quad. Never used with a real vehicle or live link. Observed simulator behaviour only.

Files: `research-tools/sitl-copter-stick-modes.py`, `research-tools/run-copter-stick-modes.sh`, `sitl-evidence/copter-stick-modes/` (CSV, JSON, simulator log), `research-tools/apply-copter-stick-claims.py` (writes the claim notes).

## Method

Take off in GUIDED to about 20 m, switch to the mode, hold a known roll stick with RC_CHANNELS_OVERRIDE for 1 simulated second (pitch and yaw centred, throttle mid), record ATTITUDE at about 20 Hz, release, return to LOITER. Each stick case was run three times. GUIDED_NOGPS was driven with SET_ATTITUDE_TARGET (10 degree roll, 0.5 thrust). SYSTEMID was started with SID_AXIS=1 (roll angle, 5 degrees, 1 to 8 Hz) and its roll variance compared with a hover reference.

## Results (final run, three attempts each)

| Mode | Input | Observed | Check |
|---|---|---|---|
| STABILIZE | roll stick 1700 | settled roll 11.23 to 11.26 deg | predicted 11.25 deg (stick fraction after RC1_DZ 20 deadzone times ATC_ANGLE_MAX 30) |
| ALT_HOLD | roll stick 1700 | settled roll 11.23 to 11.26 deg | same prediction |
| SPORT | roll stick 1600 / 1700 | peak roll rate 55.7 / 123.8 dps; roll after 1 s 31.4 / 37.4 deg | observed only |
| ACRO | roll stick 1600 / 1700 | peak roll rate 41 / 98 dps | expo curve with ACRO_RP_RATE 360, ACRO_RP_EXPO 0.3 gives about 42.5 / 100 dps (my formula) |
| DRIFT | roll stick 1700 / 1300 | yaw rate +60.7 / -60.6 dps, roll under 0.2 deg | roll stick drives yaw |
| GUIDED_NOGPS | roll 10 deg target | settled roll 10.0 deg | matches target |
| SYSTEMID | SID_AXIS=1 sweep | roll standard deviation 0.85 vs 0.04 at hover | mode started and excited the roll axis |

## Findings worth keeping

- SystemID with an attitude axis can only be entered from a mode with manual throttle (`ArduCopter/mode_systemid.cpp:100-102`). Entry from LOITER was refused with "Axis requires manual throttle"; from STABILIZE it started ("SystemID Starting: axis=1").
- `ATC_ANGLE_MAX` reads as 30 in this build (degrees, not centidegrees).
- After the SystemID sweep the vehicle lost height and hit the ground at 5.5 m/s because my fixed throttle (1400) was too low once the mode returned control. That is a test artefact, not a SystemID finding.

## Invalid and superseded runs (kept on purpose)

1. First run: the vehicle never took off. My script sent a centred-throttle override before arming and the pre-arm check "Throttle (RC3) is not neutral" refused to arm. Fixed by sending overrides only once airborne.
2. Second run: ran, but `ATC_ANGLE_MAX` was read under the wrong name so the angle prediction was wrong, SystemID was entered from LOITER (refused), and STABILIZE, ALT_HOLD and SPORT@1600 barely responded in that single run although they responded in the one before. Single runs were not reliable, so the final run repeats each case three times; the three attempts agree closely.

## Not covered

Turtle mode (needs a flipped vehicle) and Autorotate (needs a helicopter frame) were not tested. Logged SystemID data was not analysed. All numbers are one simulated quad on one build; no hardware.
