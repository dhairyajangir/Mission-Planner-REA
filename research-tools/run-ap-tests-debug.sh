#!/bin/bash
# Reconfigure the pinned-snapshot copy with --debug and rebuild/run only the three tests that failed without it.
cd ~/ap-snapshot || exit 1
LOG=~/ap-tests-logs; source ~/venv-ap/bin/activate
echo "debug configure $(date)" >> $LOG/progress.txt
python3 modules/waf/waf-light configure --board sitl --debug --no-submodule-update > $LOG/configure-debug.log 2>&1
echo "debug configure exit=$?" >> $LOG/progress.txt
python3 modules/waf/waf-light --no-submodule-update --targets tests/test_bitmask,tests/test_math_double,tests/test_rotations -j6 > $LOG/build-debug.log 2>&1
echo "debug build exit=$? $(date)" >> $LOG/progress.txt
rm -rf $LOG/debug-run; mkdir -p $LOG/debug-run
cd build/sitl/tests || exit 1
for t in test_bitmask test_math_double test_rotations; do
  ./$t > $LOG/debug-run/$t.txt 2>&1
  echo "$t exit=$?" >> $LOG/debug-run/summary.txt
done
echo "debug run done $(date)" >> $LOG/progress.txt
