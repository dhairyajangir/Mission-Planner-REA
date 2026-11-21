# Copter geofence warnings and mode changes in LOITER

Nine saved Copter simulator runs began their fence observations in LOITER. Seven reported a breach. In the other two, the simulated Copter approached a circular fence with avoidance enabled and stayed in LOITER for the 45-second observation. The earlier prototype tests exercised fences in AUTO. [Earlier simulator evidence](Custom-GCS-Prototype-Trace.md)

## What the ground station could observe

| Fence and case | Runs | Evidence received during the observation |
| --- | ---: | --- |
| Circle, return-to-launch (RTL) | 2 | Both reported a circle breach, entered RTL, and ended disarmed at 0.0 m from the local origin. In the notification case, the vehicle first reported “Circle fence in 7.9m”, then “Circle fence in 3.5m”, before reporting the breach. |
| Circle, land | 1 | The heartbeat switched from LOITER to LAND. The last recorded position was 57.3 m from the origin and the final heartbeat reported disarmed. |
| Circle, brake | 1 | The heartbeat switched to BRAKE. The breach remained active at the 12-second check. After the harness initiated recovery, the vehicle subsequently reported “Fence breach cleared”. |
| Circle, avoidance | 2 | For a 50 m circle, the largest recorded horizontal distances were 48.0 m with a 2 m margin and 42.0 m with an 8 m margin. Neither log recorded an active breach. The harness requested LAND after the observation. |
| Inclusion polygon, return-to-launch | 1 | The vehicle reported a polygon breach, entered RTL, later reported that the breach cleared, and ended disarmed at 0.0 m from the origin. |
| Inclusion polygon, brake | 2 | Both runs entered BRAKE near the north edge. One later reported the breach clearing during recovery. The other still reported an active breach at its 20-second follow-up check. Both eventually landed after harness intervention. |

Each of the seven breaches produced the same `FENCE_STATUS` tuple: active, count 1, type 3. The vehicle's text named the shape (“Circle fence breached” or “Polygon fence breached”). A ground station displaying the shape could distinguish these cases from that text. The status tuple alone was identical. [Circle captures](sitl-evidence/copter-fence-breach-circle/) and [polygon captures](sitl-evidence/copter-fence-breach-polygon/)

## How the captures were checked

For each case, the audit matched the label in the result JSON to its track CSV and notes. It checked that the timestamps were ordered, the peak horizontal distance matched the JSON at the track's 0.1 m precision, the first recorded mode after LOITER matched the reported breach response where a breach occurred, and the final mode and disarmed heartbeat agreed with the summary. All nine passed these checks. The notes, track and JSON share one telemetry receiver. Their agreement establishes consistency within each capture.

Run `python research-tools/verify-copter-geofence-captures.py` from the repository to check the saved files offline. The verifier also compares the recorded radius to horizontal distance calculated from the north and east position in each of the 17,102 rows. [Capture verifier](research-tools/verify-copter-geofence-captures.py)

Both harnesses compute horizontal distance from local north/east position and timestamp messages on receipt. The mode column repeats the last heartbeat mode observed by that recorder. Differences between message receipt times cannot establish the autopilot's internal response latency. The capture folders contain derived telemetry and summaries. They do not identify the simulator executable by hash. [Circle recorder](research-tools/sitl-copter-fence-circle-breach.py) and [polygon recorder](research-tools/sitl-copter-fence-polygon-breach.py)

Each case has one saved run. These captures cover one simulated Copter, a circle and the north edge of one inclusion polygon. Original Mission Planner screen rendering, aircraft behavior, and repeatability remain unverified.
