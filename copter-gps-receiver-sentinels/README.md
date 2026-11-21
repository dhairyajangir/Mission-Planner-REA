# How the two Mission Planner GPS receivers handle unknown values

Mission Planner 1.3.83 handled the same missing satellite count differently on its two GPS receive paths. After both had reported ten satellites, an unknown count left the primary state at 10 and set the secondary to 255. The combined-count property then returned **265**. This was a read of the released `CurrentState` object on a closed interface. The experiment did not display 265 in a Mission Planner window.

| Fields sent to both receivers | Primary satellites / HDOP | Secondary satellites / HDOP | Combined count |
| --- | --- | --- | ---: |
| Fix 3, count 10, HDOP field 85 | 10 / 0.85 | 10 / 0.85 | 20 |
| Fix 1, count 255, HDOP field 65535 | 10 / 0.85 | 255 / 655.35 | 265 |
| Fix 1, count 0, HDOP field 0 | 0 / 0.00 | 0 / 0.00 | 0 |
| Repeat the two unknown values | 0 / 0.00 | 255 / 655.35 | 255 |
| Fix 3, count 8, HDOP field 95 | 8 / 0.95 | 8 / 0.95 | 16 |

Both fix fields changed on each transition. The primary packet handler checks for the two sentinel values before assigning satellite count and horizontal dilution of precision (HDOP). The secondary handler assigns the incoming count and divides the HDOP field by 100. The retained primary count can therefore be a previous observation. In a separate browser experiment, the custom GCS displayed the primary packet's 255 value literally. [Released state observations](observations.json) · [Matching source](../mission-planner-1.3.83-source/ExtLibs/ArduPilot/CurrentState.cs) · [Protocol definitions](../mission-planner-1.3.83-source/ExtLibs/Mavlink/message_definitions/common.xml) · [Prototype browser capture](../copter-gcs-telemetry-display/unknown_measurements.png)

The probe packs each primary and secondary fixture as a MAVLink 2 frame and calls the original receive callback with Copter firmware selected. All assemblies come from the pinned portable release archive. Run `python -B copter-gps-receiver-sentinels/replay.py --replay` on Windows with the .NET Framework compiler. Omit the flag for an offline comparison of the retained values and assembly identities. [Probe](GpsReceiverProbe.cs) · [Replay](replay.py)
