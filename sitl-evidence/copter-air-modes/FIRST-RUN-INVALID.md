# First run of sitl-copter-air-modes.py (invalid, kept for the record)

The first run sent centred-stick `RC_CHANNELS_OVERRIDE` only inside each mode's observation window. During the 1.5 s pause
between modes the override expired (it times out after about 3 s of simulated time at the 5x speed-up), the simulator's
default low throttle returned and the vehicle descended and landed. Window results from that run: LOITER held 15.0 m; the
ALT_HOLD window started at 4.77 m and ended at 2.49 m; POSHOLD, BRAKE, CIRCLE, DRIFT and SPORT then ran on the ground
(altitude -0.06 to 0.09 m); SMART_RTL reported "Internal Errors 0x100000" while climbing from the ground to 9.5 m.
None of those windows is evidence of mode behaviour. The script was changed to send the sticks during every wait once
airborne, and the second run (`copter-air-modes.csv`) is the one cited. The "Internal Errors 0x100000" text appeared once
after a landed-vehicle SMART_RTL request; it did not reappear in the valid run and its cause was not investigated.
