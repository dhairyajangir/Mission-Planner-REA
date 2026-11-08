# Swarm control trace

Scope: the multi-vehicle "Swarm" feature of Mission Planner 1.3.83 (`Swarm/`), read at source level, plus a library-level probe of the one self-contained numeric piece: the `PID` class in `Swarm/Formation.cs`. No vehicle, simulator, multi-vehicle link or GUI was used. The formation, follow-leader, waypoint-leader, sequence and SRB control loops need live vehicle state and were **not run**. Nothing here shows that any swarm mode flies safely.

## Source path

- `Swarm/Swarm.cs` is the base class. It holds a `Leader`, and `Arm`, `Disarm`, `Takeoff` (switches to `GUIDED`, then `MAV_CMD_NAV_TAKEOFF` to 5 m), `Land`, `GuidedMode` and `AutoMode` walk every connected port and vehicle. All but `Land` skip the leader; `Land` sets land mode on every vehicle including the leader. `Stop` is empty.
- `Swarm/DroneBase.cs` wraps a vehicle. `SendPositionVelocity` and `SendVelocity` call `setPositionTargetGlobalInt` in `GLOBAL_RELATIVE_ALT_INT` with type masks that select position and velocity (or velocity only); `SendYaw` sends `CONDITION_YAW` when the heading differs by more than 3 degrees. `Heading` is `atan2(vy, vx)` in degrees, so it is -180 to 180, not 0 to 360.
- `Swarm/Formation.cs` converts the leader position to UTM, adds each follower's offset rotated by the negative of the leader yaw, converts back, and for ArduPlane builds `SET_ATTITUDE_TARGET` messages from four PIDs per vehicle (fixed gains created inline). For other vehicles it uses `setPositionTargetGlobalInt` and `CONDITION_YAW`. `SendCommand` reads `offsets[mav]` directly (`:99`) while `getOffsets` (`:31`) returns a default for unknown vehicles, so a vehicle without a stored offset would raise an exception (a surrounding `try` begins at `:84`; its handler was not read).
- `FollowLeader/` keeps a trail of the ground master's positions (up to 1,000), steers an "air master" to a point `Seperation` metres ahead along the waypoint line, and sends followers to successive trail points at least `Seperation` metres apart. `WaypointLeader/` also writes vehicle parameters (`RTL_ALT` set to 0 and `WPNAV_ACCEL`, `DroneGroup.cs:219`, `:229`, `:393`). `SRB/` and `Sequence/` arm, take off and move groups with the same helpers. `FollowLeader/Control.cs` sends `MAV_CMD.GUIDED_ENABLE`.
- These classes send commands to every vehicle on every connected link, with parameter writes in one mode. Test only on disposable simulators.

## Library-level probe of `PID`

`research-tools/SwarmPidProbe.cs` drives the compiled `MissionPlanner.Swarm.PID` from `mission-planner-isolated/` (the executable matches the portable release by SHA-256; the earlier data-redirected utility DLL is unrelated to this class). Files: `coverage/golden/swarm-pid-cases.csv` (211 ticks across 11 series) and `swarm-pid-summary.txt`.

The class is a port of an early ArduPilot `AC_PID`: one first-order input filter on the error, an integrator with a symmetric limit, and a derivative taken from the filtered error. The firmware's current `AC_PID.cpp` filters target, error and derivative separately, takes target and measurement, resets the integrator when `ki` is zero, and supports an anti-windup limit flag; none of that is in the port.

Observed:

- A unit step gave a P term equal to the closed-form filter response, `1 - (1 - alpha)^n` with `alpha = dt / (dt + 1 / (2 pi f))`, to within 6e-8 for two configurations. The first sample after construction is taken as-is (the filter reset), so a first sample of 1 is not filtered.
- The integrator stops at the limit (0.5 in the test) and the limit argument is used as an absolute value (-3 gave a limit of 3).
- A filter frequency argument of 0 is raised to 0.01 Hz, not treated as "no filter": alpha was 0.0062 against 0.926 for 20 Hz at the same time step, so the P term reached only 0.03 after five steps.
- **Infinite inputs are ignored, NaN is not.** The `isfinite` check (`Formation.cs:422`) tests only for infinity. After one NaN input the P, I and D terms stayed NaN for every later finite input, and `reset_I` did not clear them because the filter state itself is NaN. The class has no way to reset the filter after construction.
- `get_i` integrates on every call. Calling it twice per step doubled the integrator rate (0.2 per step instead of 0.1).
- With a time step of zero the filter never moves (P stays 0) and the I and D terms are 0. After `set_dt(0.1)` the next step produced a derivative spike: 9.26 for `kd` of 1, which equals 0.926 / 0.1.
- When an infinite input was ignored the integrator kept integrating the previous filtered value.

## Not established

All swarm control behaviour (geometry, offsets, timing, trail logic, ArduPlane attitude control, parameter writes), what the formation code does when its offset table is incomplete, and any UI behaviour. The PID gains used by the formation code were read, not exercised in a control loop.
