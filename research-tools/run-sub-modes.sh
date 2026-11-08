#!/bin/bash
cd ~/modesweep || exit 1
rm -rf sub
timeout 700 ~/venv-ap/bin/python sitl-generic-modes.py ~/modesweep/ardusub ~/modesweep/sub vectored 3 5790 MANUAL MANUAL STABILIZE,MANUAL,POSHOLD,SURFACE,CIRCLE,ACRO 1500,1500,1500,1500,1600,1500,0,0 2>&1 | tail -8
