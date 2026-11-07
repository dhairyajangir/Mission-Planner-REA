# Survey grid workflow trace

Scope: how Mission Planner 1.3.83 turns a polygon into survey waypoints, plus a library-level probe of the grid generator. No vehicle, simulator, GUI or camera hardware was used. The `GridUI` mission-building code was read but **not run**. The corridor and rotary (spiral) generators were not probed.

## Source path

- `Grid/GridPlugin.cs` adds the menu entry; `Grid/GridUI.cs` is the dialog. It receives the polygon drawn in the Flight Planner and keeps its settings in `plugin.Host.config` (`grid_*` keys).
- `GridUI.domainUpDown1_ValueChanged` (`GridUI.cs:578`) regenerates the preview on every change. It picks `Utilities.Grid.CreateCorridorAsync` (corridor), `CreateRotaryAsync` (spiral) or `CreateGridAsync` (default) from `ExtLibs/Utilities/Grid.cs`. Altitude is converted from the display unit to metres first. The "optimize for distance" check box becomes `useextendedendpoint`. The `shutter` argument is always passed `false`.
- With "cross grid" the dialog sets the **static** `Grid.StartPointLatLngAlt` to the last generated point and appends a second grid at `angle + 90` using start position `Point` (`GridUI.cs:632` onward).
- `BUT_Accept_Click` (`:1604`) turns the point list into mission commands through `AddWPtoList`. Points tagged `S` and `E` become waypoints (a point identical to the previous one is skipped). `SM` and `ME` points also become waypoints in the stop-start trigger and servo modes, and `ME` in the plain distance-trigger mode; `M` points become waypoints only for the digital-camera and repeat-servo options. Commands emitted, depending on options: `DO_SET_CAM_TRIGG_DIST`, `DO_DIGICAM_CONTROL`, `DO_REPEAT_SERVO`, `DO_SET_SERVO`, `DO_CHANGE_SPEED`, optional `TAKEOFF` (pitch 20, altitude 30 m converted to display units), `CONDITION_YAW`, `SPLINE_WAYPOINT`, and a closing `RETURN_TO_LAUNCH` or `LAND`. Splitting into several flights requires the take-off-and-land option and inserts `DO_JUMP` entries at the start of the mission.
- `AddWP` (`:887`) casts the altitude to `int` in the normal and spline paths, but not in the delay-waypoint path (`NUM_copter_delay > 0`). A 50.5 m survey altitude therefore becomes 50 in the normal path. Source reading only; not run.
- The `TAKEOFF` branch for ArduCopter and the one for other firmware (`:1639` to `:1652`) are identical.

## Generator

`Grid.CreateGrid` (`Grid.cs:354`) clamps `distance` to at least 0.1 and non-zero `spacing` to at least 0.1, projects the polygon to UTM using the zone of its first vertex, builds parallel lines at `angle` across the bounding box, intersects them with the polygon, orders the lanes by nearest-neighbour from the chosen start, and emits for each lane `S`, `SM`, optional `M` trigger points, `ME`, `E`. `shutter` is accepted and ignored. `minLaneSeparation` is multiplied by `distance` (after adding 0.5 when non-zero) and makes the lane search skip adjacent lanes. A lane crossed more than twice by the polygon (concave shapes) is split into separate pieces.

## Library-level probe

`research-tools/GridGoldenProbe.cs` calls the original compiled `CreateGrid` in `MissionPlanner.Utilities.dll` from `mission-planner-isolated/` (the earlier data-redirected copy; the grid code is unchanged, but this is not an unmodified installation). The polygon coordinates are in `coverage/golden/grid-polygons.csv` (six shapes at two sites: ArduPilot's default SITL field in zone 55 south, and Zurich in zone 32 north). `grid-cases.csv` lists 102 cases (one-factor-at-a-time variations of angle, line distance, trigger spacing, both overshoots, both lead-ins, start position, lane separation, extended end point, altitude) and `grid-points.csv` the 5,175 points returned. Every case was run twice with identical output.

Checked against the parameters, in UTM metres (an independent forward projection written for this check; not retained): lane spacing equals `distance` exactly (40.00 and 15.00 in the cases checked), consecutive trigger points are `spacing` apart, and the lane direction follows `angle` relative to UTM grid north (a 45 degree request gave a 45.0 degree UTM bearing). Because grid north is not true north, lanes at `angle = 0` in zone 55 near longitude 149.2 deviate from true north by about 1.25 degrees (the UTM grid convergence at that longitude, inferred from the lane geometry). The first trigger point on each lane is placed at a multiple of `spacing` measured from the lane's base point on the outer grid, not from the lane start, so the first step of a lane is shorter than `spacing` (10.34 m for a 40 m spacing in the baseline case). In the baseline case the 24 trigger points fall on only four distinct northings, 40 m apart, so they line up across lanes.

Other observations from the same files:

- `shutter` true or false, and a repeated first vertex in the polygon, gave identical output.
- A start position of `Home` with the test home location gave the same result as `BottomLeft` for the test polygons because the test home is nearest that corner; this does not show `Home` is ignored.
- For the `rect` and `ushape` polygons, the extended-end-point option made no difference in the baseline cases or in the cases with lane separation 3.
- With lane separation 3 and `distance` 15, the lane visiting order jumps (lane indices 0, 4, 8, 12, 7, ...) instead of going lane by lane.
- Every case that produced output starts with `S` and ends with `E`; altitude on every point equals the requested altitude.

Degenerate inputs (`coverage/golden/grid-edge-cases.csv`; the elapsed times are machine-dependent and informational):

- An empty polygon, a one-point polygon, four identical points, `distance` of 1,000,000 and a NaN latitude return an empty list without an exception. Two points and three collinear points return 20 points.
- `distance` 0 and -5 are clamped to 0.1 and return about 9,700 and 19,400 points in 2 to 3 seconds. Trigger spacing 0.05 is clamped to 0.1 and returns about 9,600 points. Whether the dialog's numeric limits prevent such values was not checked.
- Start position `Home` with a null home location throws `NullReferenceException` from the `utmpos` constructor. The dialog passes `MainV2.comPort.MAV.cs.PlannedHomeLocation`; whether that can be null was not checked.
- A polygon crossing a UTM zone boundary was converted using the zone of the first vertex and returned 64 points. Correctness of the geometry near the boundary was not checked.

## Not established

Camera footprint and overlap calculations, the corridor and spiral generators, the exact waypoints the dialog writes (only read), terrain or altitude-frame handling when the plan is uploaded, flight behaviour of any generated plan in simulation or on a vehicle, and all GUI behaviour. The golden files record what the compiled library returned for the listed inputs; they do not show the plans are suitable for flight.
