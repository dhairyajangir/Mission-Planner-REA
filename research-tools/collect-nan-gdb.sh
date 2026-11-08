#!/bin/bash
# Copy the gdb reproduction logs from WSL home into the repository evidence folder.
D='/mnt/c/Users/think/OneDrive/Documents/ChatGPT/The Drone Project/mission-planner-rea-upload/sitl-evidence/nan-wp-gdb'
mkdir -p "$D"
cp ~/modesweep/gdbnan/gdb-nan.log ~/modesweep/gdb_valid/gdb-valid.log ~/modesweep/gdb_inf/gdb-inf.log "$D/"
gdb --version | head -1 > "$D/gdb-version.txt"
sha256sum ~/modesweep/arducopter | cut -c1-64 > "$D/binary-sha256.txt"
cat "$D/binary-sha256.txt"
ls -l "$D"
