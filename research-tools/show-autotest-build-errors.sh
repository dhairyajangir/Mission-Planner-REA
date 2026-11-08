#!/bin/bash
# Show compiler/linker error lines in an autotest log in ~/autotest-logs.
# usage: show-autotest-build-errors.sh <log name> [max lines]
f=~/autotest-logs/$1
grep -n -E 'error:|Error [0-9]|fatal error|undefined reference|returned non-zero' "$f" | head -${2:-10} | cut -c1-240
