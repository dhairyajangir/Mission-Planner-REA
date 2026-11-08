#!/bin/bash
# Install the pymavlink shipped inside the pinned ArduPilot snapshot (modules/mavlink/pymavlink) into the test venv,
# because the pip release (2.4.50) lacks MAVLINK_IFLAG_SYSID32 that the snapshot's autotests need.
source ~/venv-ap/bin/activate
echo "before: $(pip list 2>/dev/null | grep -i pymavlink)"
cd ~/ap-snapshot/modules/mavlink/pymavlink || exit 1
pip install --no-deps --force-reinstall . 2>&1 | tail -3
echo "after: $(pip list 2>/dev/null | grep -i pymavlink)"
python3 -c "from pymavlink import mavutil; print('SYSID32 flag:', hasattr(mavutil.mavlink,'MAVLINK_IFLAG_SYSID32'))"
