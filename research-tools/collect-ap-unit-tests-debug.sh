#!/bin/bash
D='/mnt/c/Users/think/OneDrive/Documents/ChatGPT/The Drone Project/mission-planner-rea-upload/ap-unit-tests-evidence'
LOG=~/ap-tests-logs
mkdir -p "$D/debug-rerun"
cp $LOG/debug-run/*.txt "$D/debug-rerun/"
grep -E "Debug build|Board" $LOG/configure-debug.log > "$D/debug-rerun/configure-summary.txt"
tail -5 $LOG/build-debug.log | cut -c1-160 > "$D/debug-rerun/build-tail.txt"
cat >> "$D/NOTES.md" <<'EOF'

Failures without `--debug`: `test_bitmask`, `test_math_double` (ConstrainDouble) and `test_rotations` (TestFailedGetLinux) are death tests
that expect an abort after an internal error. `AP_InternalError::error` panics only when `HAL_DEBUG_BUILD` is defined
(`libraries/AP_InternalError/AP_InternalError.cpp:18`). After `waf configure --board sitl --debug --no-submodule-update` and
rebuilding only those three targets, all three passed (27, 12 and 5 tests; see `debug-rerun/`). The other 72 programs were run only in
the non-debug build. A first attempt to rebuild with `--debug` failed on a `git submodule status` call in the throwaway repository and is
not counted (the binaries it re-ran were the non-debug ones).
EOF
ls "$D/debug-rerun"
