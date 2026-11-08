#!/bin/bash
# List the autotest test names for a vehicle that have no PASSED/FAILED line yet in the given logs.
# usage: autotest-remaining.sh <vehicle e.g. Copter> <log1> [<log2> ...]    (logs are names in ~/autotest-logs)
VEH=$1; shift
source ~/venv-ap/bin/activate
cd ~/ap-snapshot || exit 1
python3 Tools/autotest/autotest.py --list-subtests-for-vehicle "$VEH" 2>/dev/null | tr ' ' '\n' | sed 's/^test\.'"$VEH"'\.//' | grep -v '^$' | sort -u > /tmp/all-tests.txt
for l in "$@"; do cat ~/autotest-logs/$l; done | grep -E '^AT-[0-9.]+: (PASSED|FAILED): "' | sed -E 's/^AT-[0-9.]+: (PASSED|FAILED): "([^ ]+) .*/\2/' | sort -u > /tmp/done-tests.txt
echo "all: $(wc -l < /tmp/all-tests.txt)  done: $(wc -l < /tmp/done-tests.txt)"
comm -23 /tmp/all-tests.txt /tmp/done-tests.txt > ~/autotest-logs/$VEH-remaining.txt
echo "remaining: $(wc -l < ~/autotest-logs/$VEH-remaining.txt)"
head -60 ~/autotest-logs/$VEH-remaining.txt | tr '\n' ' '
