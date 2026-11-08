#!/bin/bash
# Run the generic armed mode test for Sub and Blimp (WSL, disposable SITL) and print the summaries.
cd ~/modesweep || exit 1
rm -rf sub blimp_run
timeout 800 ~/venv-ap/bin/python sitl-generic-modes.py ~/modesweep/ardusub ~/modesweep/sub vectored 3 5790 MANUAL MANUAL STABILIZE,MANUAL,POSHOLD,SURFACE,CIRCLE,ACRO 1500,1500,1500,1500,1600,1500,0,0 2>&1 | tail -8
echo ======= BLIMP
timeout 800 ~/venv-ap/bin/python sitl-generic-modes.py ~/modesweep/blimp ~/modesweep/blimp_run blimp 4 5800 MANUAL MANUAL MANUAL,VELOCITY,LOITER,HOLD,LAND,RTL 1500,1400,1500,1500,0,0,0,0 2>&1 | tail -8
