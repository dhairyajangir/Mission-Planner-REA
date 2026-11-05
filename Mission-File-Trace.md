# Mission file handling

Scope: selected Mission Planner 1.3.83 source paths and synthetic local files tested through the distributed `MissionPlanner.Utilities.dll`. The harness did not run the planner screen or upload a mission to a vehicle.

## Source paths

`ExtLibs/Utilities/MissionFile.cs:18` reads QGC WPL text into `Locationwp` records. It accepts a header containing `QGC WPL`, ignores lines beginning with `#`, inserts an empty home record if the first parsed sequence is not zero, and reads frame, command, four parameters, latitude, longitude and altitude. The parsing path does not copy the text file's current-item or autocontinue fields into `Locationwp`. `GCSViews/FlightPlanner.cs:995` passes the resulting list to the planner, with separate handling for fence and rally selections.

For a JSON document whose first line begins with `{`, the source planner calls `MissionFile.ReadFile` and `ConvertToLocationwps` (`FlightPlanner.cs:1858`). That converter adds the planned home, accepts items marked `SimpleItem`, expands the listed items within certain `ComplexItem` structures, and skips other item types (`MissionFile.cs:105`). The save path uses `ConvertFromLocationwps` and `WriteFile` for a `.mission` file (`FlightPlanner.cs:5864`). The source conversion sets each exported item's frame to the single supplied frame; the `Locationwp` to `Item` conversion in `locationwp.cs:138` does not set `type` or `autoContinue`. These are source observations; source-to-distributed-binary equivalence is not established.

## Library observations

The original utility library read a two-row WPL fixture as home and one waypoint. A file starting with sequence 1 yielded an inserted all-zero home and the same waypoint. Changing the waypoint's current and autocontinue values left the fields printed by the harness unchanged. This checks one text fixture and the printed fields, not every command, frame or invalid-file path.

Using that two-item list, the distributed library's JSON export produced one mission item with `type: null` and `autoContinue: false`. Reading the generated file through the same library's `ConvertToLocationwps` returned only the home record. As a control, setting the generated item's type to `SimpleItem` in memory before conversion returned both home and waypoint. The planner source calls these same named conversion methods, but no GUI save-and-open test was performed; do not infer an end-to-end UI result from this harness alone.

An attempt to open the isolated application copy for a UI check encountered a Windows Firewall permission prompt covering the planner. No response was sent to the prompt. The isolated application process was stopped and its window was confirmed closed. The prompt was visually observed but no separate screenshot was retained. The GUI file workflow therefore remains unverified.

Inputs, generated JSON, full harness output and file hashes are under `sitl-evidence/mission-file-probe/`. The harness is `research-tools/MissionFileProbe.cs`, and `summarize-mission-file-probe.py` records the bounded observations. Full survey structures, localization, fences, rally points and other mission commands remain untested.

## Selected plan conversion cases

A second library harness read a synthetic plan containing a home position, one `SimpleItem`, a `ComplexItem` with two nested transect items, and one unrecognized item. It returned four `Locationwp` records: home, the simple item and the two nested items. The unrecognized item produced no record. The simple fixture's null second parameter became zero in the returned record. Removing `TransectStyleComplexItem` from that complex item caused `NullReferenceException`; shortening the simple item's parameter list from seven entries to six caused `ArgumentOutOfRangeException`. The harness caught both exceptions and continued. This does not establish how the GUI reports those errors or how arbitrary surveys are represented. Fixtures, output and hashes are under `sitl-evidence/mission-plan-probe/`.

## Additional WPL import cases

The distributed Utilities library was called on five synthetic text fixtures. A nine-field waypoint row was skipped, and the following sequence-2 waypoint was returned as the second record. Two rows with sequence 1 were both returned as separate records, with their different altitudes. A `NaN` latitude was returned as `NaN`. A header containing `QGC WPL` inside a longer, unexpected string was accepted; a missing sequence 1 was also accepted. No exception was returned to this harness for these cases.

The matching source checks the header with `Contains`, skips rows with at most nine split fields, and does not validate the sequence after its initial home check (`MissionFile.cs:18`). These observations apply to this library call, not the GUI. The fixture files, output, source and executable are in `sitl-evidence/waypoint-import-edges/`; `research-tools/summarize-waypoint-import-edges.py` checks their hashes and the REA entry for `WaypointFile.ReadWaypointFile` (token `0x060005ce` in the inspected build). The next section covers limited simulated upload tests for the NaN fixture; later validation of the other cases remains untested.

## NaN latitude through library upload

Two separate source-built Copter SITL runs imported the same synthetic WPL fixture containing a `NaN` latitude. Each used the original library to upload and read back a valid two-item baseline, then started replacing it with the synthetic waypoint. In the integer-format run, the captured `MISSION_ITEM_INT` encoded the latitude as `-2147483648`; the simulator returned `MAV_MISSION_INVALID_PARAM5_X`. The mission count and item 1 then read back as the baseline values. This readback does not establish that every mission field was unchanged.

In the floating-point run, the captured `MISSION_ITEM` contained a NaN latitude. The simulator-side connection closed, and its log reported `ERROR: Floating point exception - aborting`; the library timed out while sending the item and again on the attempted mission-count readback. This was one run. The capture and log do not prove the exception's exact cause, and post-failure mission state was not read back. No conclusion about physical aircraft or other builds follows from this observation.

Matching source routes floating mission items through `AP_Mission::convert_MISSION_ITEM_to_MISSION_ITEM_INT`, which checks latitude with `check_lat` before scaling (`AP_Mission.cpp:1614`; `AP_Math/location.cpp:39`). The precise instruction that raised the observed exception has not been established. `research-tools/summarize-wpl-nan-upload.py` decodes the saved traffic and checks the outcome logs under `sitl-evidence/command-ack-wpl_nan_int/` and `command-ack-wpl_nan_float/`. GUI import, full mission recovery, repetition and physical behavior remain untested.
