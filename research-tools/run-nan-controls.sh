#!/bin/bash
# Run sitl-nan-wp-gdb.py for the valid and infinity controls (WSL).
cd ~/modesweep || exit 1
for v in valid inf; do
  rm -rf "gdb_$v"
  ~/venv-ap/bin/python sitl-nan-wp-gdb.py ~/modesweep/arducopter ~/modesweep/gdb_$v $v 2>&1 | grep -v 'EOF on TCP' | tail -4
  echo "-- $v SIGFPE count: $(grep -c 'received signal SIGFPE' gdb_$v/gdb-$v.log)"
done
