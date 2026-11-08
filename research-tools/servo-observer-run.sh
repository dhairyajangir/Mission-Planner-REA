#!/bin/bash
# Wrapper so the observer can be started with Start-Process (no spaces in its path or arguments): records SERVO_OUTPUT_RAW for 90 s.
source ~/venv-ap/bin/activate
python3 ~/sitl-servo-observer.py 90 ~/servo-observer.csv > ~/servo-observer.out 2>&1
