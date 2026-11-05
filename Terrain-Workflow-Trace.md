# Terrain request and response trace

Scope: selected Mission Planner 1.3.83 and pinned ArduPilot source paths, REA records for the distributed Utilities assembly, and two local Copter SITL runs using a synthetic elevation tile. This does not establish real-world terrain accuracy or full application behavior.

## Source and binary anchors

`MissionPlanner.Utilities.TerrainFollow` subscribes to incoming `TERRAIN_REQUEST` and `TERRAIN_REPORT` messages. For a request, `ReceivedPacket` records the last request and schedules `QueueSendGrid`; requests arriving while `issending` is true return without starting another worker. The worker iterates 56 mask bits and calls `SendGrid` for each requested 4×4 block. `SendGrid` samples `srtm.getAltitude` for 16 points, returns without sending if a sample is invalid, and otherwise sends `TERRAIN_DATA` with the original request's coordinates, spacing and bit. `checkTerrain` sends `TERRAIN_CHECK` for a coordinate. These are selected source observations, not an exhaustive concurrency analysis.

The REA index maps the distributed `MissionPlanner.Utilities.dll` responder methods, IL hashes and static call references in `mission-planner-binary-evidence/terrain-method-map.json`. The runtime tests below used a modified Utilities assembly with redirected data-path methods, so the REA records anchor the distributed binary rather than proving identical behavior of every modified method.

In ArduPilot's `libraries/AP_Terrain/TerrainGCS.cpp`, `request_missing` asks for missing 4×4 blocks using the complement of the cached bitmap, subject to its conditions. `handle_terrain_data` looks for a cached grid with matching coordinates and spacing, checks that the bit is below 56, copies the 16 heights and marks that bit present. `handle_terrain_check` requests a terrain report for the supplied coordinate. These source statements are subject to the firmware's feature configuration.

## Synthetic-tile simulator tests

A workspace `S36E149.hgt` fixture contains 1,201×1,201 big-endian signed samples, all **321 m**; its SHA-256 is `cca981043973562c5c477e8f5ca12a07a19f4fbbe0a7cec3cbb26c7500660be5`. This is synthetic and must not be used for real navigation. The probe explicitly set its SRTM directory to that fixture and the test utility returned a valid 321 m sample at the simulator's home coordinate.

The first run sent terrain checks but did not explicitly request telemetry streams. The simulator reported missing terrain, but no `TERRAIN_REQUEST` or `TERRAIN_DATA` frames appeared in the captures during the probe's observation window; the probe timed out. The cause of the absence was not isolated. Its logs and capture are retained in `sitl-evidence/command-ack-terrain_fixture/summary.json`.

In a fresh run, the probe explicitly requested all streams at 4 Hz. It observed 16 terrain requests; the responder sent 40 terrain-data frames, each containing 16 heights of 321 m. An independent MAVLink decoder verified each transmitted block's grid identity and bit against a captured request. The simulator then reported 321 m for the checked coordinate, with 40 blocks loaded and 16 pending at that point. Captured vehicle heartbeats were disarmed. Evidence is in `sitl-evidence/command-ack-terrain_fixture_stream/summary.json`; `research-tools/summarize-terrain-fixture.py` decodes both runs.

The first run and the stream-enabled run are separate simulations: the comparison does not prove that stream configuration alone caused the different outcomes. The 16 pending blocks mean the run does not establish completion of the entire terrain grid. The probe used the original ArduPilot and MAVLink DLLs with the patched Utilities DLL; it did not use the full UI, an online provider, real elevation data, a physical vehicle, or navigation based on the resulting heights.

## Sloped synthetic tile

A separate fixture assigns each HGT sample `row + 2 × column`, with row zero at the tile's north edge. Its SHA-256 is `e94fa1713b8ebde9e83b48273226ee5c0b913523a0be746f28d55b577ea89fcd`. In a fresh disarmed SITL run with streams enabled, the responder sent 41 terrain blocks. The independent decoder checked all 656 transmitted heights against the synthetic gradient and spherical offsets used for the captured grid positions; all matched the calculated integer values. Swapping the within-block east and north sample axes would have changed 492 of those values, so the test distinguishes that particular ordering error.

At the checked coordinate, the analytic fixture height is approximately 832.465 m. SITL reported approximately 831.995 m, within 1 m, with 40 blocks loaded and 16 pending in that report. The additional captured block and the report are on separate directional streams, so their timing is not inferred from capture order. Evidence is in `sitl-evidence/command-ack-terrain_slope/summary.json`; `research-tools/summarize-terrain-slope.py` validates the complete fixture and captured samples. This is a synthetic, locally generated tile and does not test real data, a full grid, rendering, or navigation.

## Void samples

A third fixture filled the entire HGT tile with the signed value −32,768. The test utility returned an invalid sample at the checked coordinate. During a 20-second observation with streams enabled, an independent decoder found 29 terrain requests and no outbound `TERRAIN_DATA` frames; all 83 captured terrain reports showed pending blocks and zero loaded blocks. The probe itself read 23 requests and 66 pending reports; the reason for the count difference was not isolated. Evidence is in `sitl-evidence/command-ack-terrain_invalid/summary.json` and `research-tools/summarize-terrain-invalid.py`. This covers an all-void synthetic tile, not mixed valid and void samples, downloads, other elevation formats or indefinite operation.

## One dropped block

With the flat synthetic tile and streams enabled, a frame-aware relay dropped the first `TERRAIN_DATA` frame for grid bit 0. The uplink capture then contained another frame for the same grid and bit, which the relay delivered. The downlink capture contained 22 requests for that grid with bit 0 set, including requests whose mask contained only that bit. SITL also reported 321 m for the checked coordinate. `sitl-evidence/command-ack-terrain_drop_one/summary.json` and `research-tools/summarize-terrain-retry.py` preserve and decode the input, forwarded and dropped frames.

The captures establish a matching retransmission and delivery through the local relay. They do not contain a per-block vehicle acknowledgement, and separate directional captures do not by themselves establish the precise timing of each request relative to that retransmission. This was one deliberately dropped frame in one simulator run, not a test of sustained loss or real terrain.
