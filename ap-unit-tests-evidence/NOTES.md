Built from a copy of `ardupilot-source/ardupilot-master` (pinned snapshot, commit 72b238201f5ea3b556e3809b2ec704fcf701474a)
without `modules/ChibiOS` and `modules/gsoap`, inside WSL Ubuntu 24.04 (g++ 13.3). The copy has no `.git`; the waf build calls git
for version headers, so a throwaway empty repository was created in the copy and any commit hash printed by the build is NOT the
pinned commit. First configure: `--board sitl` without `--debug`.

Failures without `--debug`: `test_bitmask`, `test_math_double` (ConstrainDouble) and `test_rotations` (TestFailedGetLinux) are death tests
that expect an abort after an internal error. `AP_InternalError::error` panics only when `HAL_DEBUG_BUILD` is defined
(`libraries/AP_InternalError/AP_InternalError.cpp:18`). After `waf configure --board sitl --debug --no-submodule-update` and
rebuilding only those three targets, all three passed (27, 12 and 5 tests; see `debug-rerun/`). The other 72 programs were run only in
the non-debug build. A first attempt to rebuild with `--debug` failed on a `git submodule status` call in the throwaway repository and is
not counted (the binaries it re-ran were the non-debug ones).
