#!/bin/bash
# Re-run the failing unit tests directly, capture their gtest output, and list all test programs with their source libraries.
cd ~/ap-snapshot/build/sitl/tests || exit 1
mkdir -p ~/ap-tests-logs/failures
for t in test_bitmask test_math_double test_rotations; do
  ./$t > ~/ap-tests-logs/failures/$t.txt 2>&1
  echo "== $t exit=$?"
  grep -E "FAILED|Failure|Expected|Which is|Actual|actual|expected|PASSED|tests ran" ~/ap-tests-logs/failures/$t.txt | head -12
done
ls | grep '^test_' | wc -l
