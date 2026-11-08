# Antenna tracker trace

Scope: how Mission Planner 1.3.83 turns the vehicle position into antenna-tracker commands, plus a library-level probe of the bearing and elevation maths and of the three output drivers. No tracker hardware, servo controller, vehicle or simulator was used; the serial port was an in-memory stand-in. The dialog, real serial behaviour and any device response were **not** tested. This is Mission Planner's own serial-driven tracker, not the ArduPilot AntennaTracker vehicle firmware.

## Source path

- `Antenna/TrackerUI.cs` is the dialog; `Antenna/TrackerGeneric.cs` wires its controls to one of three drivers in `ExtLibs/Antenna/` (`Maestro`, `ArduTracker`, `DegreeTracker`, all implementing `ITrackerOutput`).
- `BUT_connect_Click` (`TrackerGeneric.cs:87`) builds the driver, opens the serial port, copies ranges, trims, reversal and PWM settings from the dialog, calls `Init`, `Setup` and `PanAndTilt(0, 0)`, then starts a background thread.
- The thread (`mainloop`, `:207`) sends `MAV.cs.AZToMAV` and `MAV.cs.ELToMAV` to `PanAndTilt` every 100 ms. It catches and discards every exception, so a failing port is silent.
- `AZToMAV`, `ELToMAV` and `DistToHome` are in `ExtLibs/ArduPilot/CurrentState.cs` (`:1807`, `:1827`, `:1763`). The tracker position is `TrackerLocation`, which falls back to the home location when the tracker longitude is exactly 0.
- `TXT_panrange_TextChanged` (`TrackerGeneric.cs:238`) parses the entered range and then overwrites it with 360, so the pan-trim slider always spans plus or minus 180 whatever range is entered. Source reading only.
- The `PanReverse` and `TiltReverse` getters are inverted in `ArduTracker` and `DegreeTracker` (they return true when not reversed). The dialog only sets them, so this has no effect on the probe output.

## Drivers

- `Maestro` writes Pololu "compact protocol" commands: `0x87` speed and `0x89` acceleration per channel in `Setup`, then `0x84` set-target (channel 0 pan, channel 1 tilt, microseconds times four in two 7-bit bytes).
- `ArduTracker` writes the ASCII line `!!!PAN:<pwm>,TLT:<pwm>\n`, with PWM values computed like Maestro's, but truncates the wrapped angle to a whole degree first.
- `DegreeTracker` writes the same line shape with angles in tenths of a degree. It ignores trim, range and reversal.

## Library-level probe

`research-tools/AntennaTrackerProbe.cs` runs the compiled drivers and `CurrentState` from `mission-planner-isolated/` (the earlier data-redirected utility DLL; the antenna, comms and ArduPilot DLLs are unchanged). The driver output goes to an in-memory `ICommsSerial` placed in `SerialPort._baseport`, a seam the library provides. Files: `coverage/golden/tracker-geometry.csv` (165 positions), `tracker-output.csv` (792 driver calls across four configurations) and `tracker-probe-output.txt`.

Geometry, compared with a spherical great-circle bearing and distance computed in the probe:

- At 500 m from trackers at the ArduPilot SITL field (southern hemisphere), Zurich and latitude 70, `AZToMAV` was within 0.007 degrees of the great-circle bearing. At 20 km the worst error was 0.07, 0.10 and 0.26 degrees respectively.
- `DistToHome` ran about 0.1 per cent longer than the great-circle distance (500.56 m for 500 m, constant 111,319.5 m per degree).
- Elevation for a 100 m height difference at 500 m came out at 11.30 degrees; for -50 m at 500 m, -5.70.
- The result is **zero azimuth, zero elevation and zero distance** when the tracker latitude is exactly 0, when the tracker longitude is exactly 0 and no home is set, when the vehicle is at latitude and longitude 0, or when the vehicle is directly above the tracker (elevation 0 rather than 90). These come from the `lat == 0`, `TrackerLocation.Lat == 0` and `dist == 0` guards.
- A tracker at longitude 179.999 and a vehicle at -179.999 (about 220 m apart) gave a distance of 39,466 km, because longitudes are subtracted without wrapping.

Driver output, pan range 360 degrees (plus or minus 180), tilt range 90, 1000 microsecond range centred at 1500:

- `Maestro` and `ArduTracker` agree on PWM values for 126 of the 132 compared pan/tilt pairs in the first two configurations. The 6 differences are all at pan 359.9, where Maestro gives 1499 and ArduTracker 1500 (its whole-degree truncation). Pan 0 gives 1500, 90 gives 1750, 180 gives 2000, 181 gives 1002 (the seam wraps through the full range), 270 gives 1250; tilt 0 gives 1500, 45 gives 2000, -20 gives 1277.
- With pan trim 20, tilt trim 5 and reversal on, pan 0 gives 1555 and tilt 0 gives 1555, tilt 45 gives 1055. `DegreeTracker` ignores all three and writes the untrimmed angle.
- `ArduTracker` pan 359.9 gives 1500, which is the same as pan 0 (the wrapped -0.1 degree is truncated to zero). `DegreeTracker` writes `3599` and for negative angles `-0100`, which is one character wider than the `0000` pattern.
- Maestro with a 360-degree pan range and a tilt range above 120 degrees takes a "flip" branch for targets behind the tracker. With tilt range 180, pan 135 and any tilt from 10 to 90 produced the same tilt pulse (2000 microseconds), because `Tilt(180 - tilt)` falls outside plus or minus 90. With tilt range 360 the same inputs gave 1972, 1875 and 1750.

## Not established

Behaviour on a real Maestro, servos or the receiving firmware of the other two drivers, serial timing and failure handling beyond the in-memory port, the dialog, and use of the Maestro "get position" paths. The comparison with great-circle values shows the library's flat-earth approximation; it does not show the tracker points at the vehicle.
