# Copter GPS fix loss on the Mission Planner flight display

Mission Planner 1.3.83 showed a red **GPS: No Fix** indication while its Copter state could still hold a position and altitude. Which position it kept depended on the message source. The probe delivered eight nominal synthetic messages to the release receive callback over a closed interface. [Recorded state](sitl-evidence/copter-gps-fix-hud/observed.csv)

| Input to the ground station | Result in the release state |
| --- | --- |
| Raw GPS, 3D fix, then no fix with the same coordinates | Fix changed from 3 to 1. Position and altitude above sea level stayed at 10°, 20°, 101 m. Satellite count changed from 12 to 4 and HDOP from 0.85 to 2.75. |
| Raw GPS, still no fix, now reporting zero coordinates and altitude | Latitude, longitude and altitude above sea level all became zero. |
| Raw GPS recovered with a new position | Fix returned to 3, with 10.01°, 20.01° and altitude above sea level 102 m. Relative altitude remained 0 m throughout the raw-GPS-only sequence. |
| Valid global-position message, followed by raw GPS reporting no fix and zero coordinates | Fix changed to 1. The global position of 10.1°, 20.1°, 123 m above sea level and 12 m relative altitude stayed in state. |
| New global position while GPS still reported no fix | Position advanced to 10.11°, 20.11°, 124 m above sea level and 13 m relative altitude. GPS recovery changed fix status to 3 and kept those global-position values. |

The form designer binds the HUD's primary fix property to `CurrentState.gpsstatus`. The probe passed that property into the release HUD and used its software renderer in English text mode. The first crop reads “GPS: 3D Fix”. With the last known position retained, the second reads “GPS: No Fix” in red. The recovered crop matched the first pixel for pixel. The crops show the GPS indicator. The numeric location and altitude observations come from the state object. [3D fix](sitl-evidence/copter-gps-fix-hud/raw-3d.png) · [No fix](sitl-evidence/copter-gps-fix-hud/raw-lost-last-position.png) · [Recovery](sitl-evidence/copter-gps-fix-hud/raw-recovered.png)

The source has separate cases for `GPS_RAW_INT` and `GLOBAL_POSITION_INT`. A raw GPS packet updates fix quality regardless of the active position source. A global packet with valid coordinates makes global position authoritative for latitude, longitude and altitude above sea level. This experiment supplied every transition as an explicit packet. Receiver silence, timers, the map marker and aircraft behavior remain unmeasured. [CurrentState](mission-planner-1.3.83-source/ExtLibs/ArduPilot/CurrentState.cs) · [Flight Data bindings](mission-planner-1.3.83-source/GCSViews/FlightData.Designer.cs)

Run `python -B research-tools/verify-copter-gps-fix-hud.py <new-output-directory>` on Windows with .NET Framework and Pillow installed. The verifier extracts libraries from the portable ZIP, compiles the harness, checks eight observed rows and compares all three HUD crops. The initial build lacked the .NET Standard facade required by the released MAVLink DLL. The runner now references the framework copy. [Harness](research-tools/CopterGpsFixHudProbe.cs) · [Replay verifier](research-tools/verify-copter-gps-fix-hud.py) · [Verification results](sitl-evidence/copter-gps-fix-hud/verification.json)
