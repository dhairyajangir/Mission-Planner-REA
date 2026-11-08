# Fork changes trace

Scope: the first changes to our own ArduPilot fork. The fork is a git repository (`~/ardupilot-fork` inside the `Ubuntu-E` WSL distribution) whose first commit is the unchanged upstream snapshot `72b238201f5ea3b556e3809b2ec704fcf701474a` (tag `baseline-72b23820`, branch `upstream-snapshot`); our commits are on branch `ours`. ArduPilot is GPLv3; all licence files are kept. This is a source change plus unit and simulator checks, not a flight-tested product.

Files: `fork-patches/` (the three patches as `git format-patch` output, `COMMITS.txt`, `BASELINE.txt`), `research-tools/fork-change1-test.cpp` (the unit test), `research-tools/fork-change1.sh` (red, green and green2 stages), `research-tools/fork-change1-sitl.sh` (simulator replay), `research-tools/make-ardupilot-fork.sh`, `research-tools/export-fork.sh`, `sitl-evidence/fork-change1/` (logs). A bundle of the whole fork (about 400 MB) is at `E:\DroneProject\ardupilot-fork.bundle`, outside this repository.

## Changes

| Commit | What |
|---|---|
| `0af0c875` | New unit test `libraries/AP_Math/tests/test_check_latlng.cpp`. It enables `FE_INVALID` trapping (as SITL does) around `check_lat/check_lng/check_latlng` calls with NaN and infinity, and checks the integer limits. |
| `2d30d4a5` | `check_lat(float)` and `check_lng(float)` now test `isfinite()` before the ordered comparison. |
| `bc3373d2` | `check_lat(int32_t)` and `check_lng(int32_t)` compare against exact integer limits (900000000L, 1800000000L). |

## Results

- **Unpatched (test commit only):** the test process died with exit 136 (SIGFPE) in the NaN case, the same crash found earlier in the simulator (`Mission-File-Trace.md`). The integer-limit test also failed on 4 values (900000001, -900000001, 1800000001, -1800000001 were accepted).
- **After `2d30d4a5`:** the NaN test passes; only the integer-limit test still fails.
- **After `bc3373d2`:** all 3 tests pass.
- **Simulator replay** (Copter SITL built from the fork, float `MISSION_ITEM` sent by pymavlink under gdb): NaN latitude is now rejected with `MISSION_ACK` type 10 (`MAV_MISSION_INVALID_PARAM5_X`) and no SIGFPE is logged; before, the same test crashed the simulator. Infinity was already rejected with type 10 and is unchanged. The "valid" control still returns type 1 (generic error) as in the baseline run, so it is a weak control and still shows no clean accept.

## Interpretation and limits

- The integer-limit defect: my explanation is that ArduPilot builds with `-fsingle-precision-constant`, so `90*1e7` is a float constant and the integer is compared as a float, where 900000001 rounds onto 900000000. The exact-integer fix makes the test pass, which is consistent with that, but I did not inspect the compiler flags or the generated code.
- On real flight hardware the NaN comparison simply returns false (no trap), so the NaN fix mainly changes simulator behaviour and makes the intent explicit. The integer-limit fix changes behaviour on all builds, but only for values within about 32 units of the limit (roughly 3 mm).
- Unit tests and one simulator replay only. The full ArduPilot test suites were not rerun on the fork.

## Failed attempts (kept on purpose)

1. First version of the unit test did not link: it lacked `const AP_HAL::HAL& hal = AP_HAL::get_HAL();` which every HAL-based test defines. Fixed, and the test commit was recreated so the fork history has one clean test commit.
2. My first test expected `check_lat(int32_t(900000001))` to be rejected on unpatched code and put it in the same test as other checks. It failed on unpatched code, which exposed the integer-limit defect; I then split it into its own test so each fix has its own red and green.
