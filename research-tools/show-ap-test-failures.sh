#!/bin/bash
cd ~/ap-tests-logs/failures || exit 1
for t in test_bitmask test_math_double test_rotations; do
  echo "=== $t"
  grep -B1 -A6 'Failure' $t.txt | head -28
done
echo "=== bitmask source 45-72"; sed -n 45,72p ~/ap-snapshot/libraries/AP_Common/tests/test_bitmask.cpp
echo "=== math_double source 84-93"; sed -n 84,93p ~/ap-snapshot/libraries/AP_Math/tests/test_math_double.cpp
echo "=== rotations source 160-178"; sed -n 160,178p ~/ap-snapshot/libraries/AP_Math/tests/test_rotations.cpp
