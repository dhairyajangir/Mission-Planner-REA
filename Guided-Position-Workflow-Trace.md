# Guided position workflow: Mission Planner and Copter

## Scope and provenance

This trace combines the Mission Planner 1.3.83 matching-tag source, static REA metadata for its distributed `MissionPlanner.ArduPilot.dll`, the pinned ArduPilot source at `72b238201f5ea3b556e3809b2ec704fcf701474a`, and one source-built Copter SITL run. The probe called the distributed library; it did not exercise the graphical interface. The simulator remained disarmed.

## Source path

The Flight Data map's Go Here handler checks for an open connection, requests an altitude when its stored guided altitude is zero, and rejects a zero clicked latitude or longitude. It constructs a waypoint from the clicked position and stored altitude and frame, then calls `setGuidedModeWP` (`GCSViews/FlightData.cs:3018`).

The targeted library overload returns immediately if any of latitude, longitude or altitude is zero. Otherwise it sets the waypoint command and, by default, attempts to enter GUIDED if the stored mode is not GUIDED. For ArduPlane, it uses the mission-item path and checks the result. For other firmware, it sends a `SET_POSITION_TARGET_GLOBAL_INT` position target in `GLOBAL_RELATIVE_ALT_INT`; it does not use the supplied waypoint frame on that branch. Exceptions within the method are logged and swallowed (`ExtLibs/ArduPilot/Mavlink/MAVLinkInterface.cs:4420`). The lower-level sender scales coordinates by 10 million, casts them to integers, constructs the type mask and updates the library's stored guided coordinates before sending (`MAVLinkInterface.cs:4497`). These are source observations, not proof the user interface displayed success or that a vehicle acted.

The inspected distributed assembly has REA index entries for the two `setGuidedModeWP` overloads at tokens `0x06000487` and `0x06000488` and `setPositionTargetGlobalInt` at `0x0600048b`. The index belongs to this particular binary; tokens are not stable across builds. The assembly SHA-256 is `107fa88e20dbf4c6b2e23f4a71d79030867b61cfe7b596cbc9f63b7f86187c8c`.

In the pinned Copter source, the global-position handler returns immediately unless the current flight mode reports guided operation. It validates the position and altitude frame and, for position-only inputs, calls the guided controller's `set_destination` (`ArduCopter/GCS_MAVLink_Copter.cpp:1079`). This source trace does not establish that a particular target was accepted or reached.

## Disarmed simulator experiment

The original library opened one source-built Copter SITL through a frame-aware loopback relay. The probe called the overload with automatic mode switching disabled. Three calls individually set latitude, longitude or altitude to zero. A valid target was then sent while the simulator reported disarmed STABILIZE. The probe requested GUIDED, waited for a disarmed GUIDED heartbeat, and sent a second valid target. It exited successfully with a final disarmed GUIDED heartbeat.

Independent decoding of client-to-simulator bytes found exactly two `SET_POSITION_TARGET_GLOBAL_INT` frames, in the order of the two valid calls. Their frame was 6 (`GLOBAL_RELATIVE_ALT_INT`), type mask 65016, and destination system/component 1/1. The captured coordinates and altitudes were `(-35.3631, 149.1651, 11 m)` and `(-35.3632, 149.1652, 12 m)`. Two `SET_MODE` frames appeared between them. No packet corresponding to the three zero-value inputs appeared in this capture. The relay reported no errors and no dropped bytes.

The script `research-tools/summarize-guided-position.py` independently decodes and checks the capture. Source, executable, raw directional captures, probe output, relay output and the decoded summary are preserved under `sitl-evidence/command-ack-guided_position/`. The simulator binary SHA-256 was `646e5b5a2d294a200dfeee25558963ca50141b6dc5c08c1dd6880607e0c35a57`.

This disarmed test observes packet creation and a mode heartbeat only. In particular, source inspection indicates that the first target is ignored by the pinned Copter handler while outside guided operation; the experiment did not instrument the handler to observe that return.

## Airborne simulator experiment

A separate probe used the original Mission Planner library and the same source-built Copter through the local relay. The first attempt, preserved in `sitl-evidence/command-ack-guided_flight/`, failed normal arming with `PreArm: Need Position Estimate`; no simulated takeoff occurred. The retry waited longer for initialization and did not bypass arming checks. Its first arm command and takeoff command returned accepted. After the reported relative altitude exceeded 3.5 m, the probe sent a position target approximately 8.9 m north at 5 m relative altitude. The probe then selected LAND and observed a disarmed LAND heartbeat.

The independent decoder `research-tools/summarize-guided-flight.py` checks both captured directions and the probe log. It found the one position target at `(-35.3631809, 149.1652298, 5 m)`. The last logged position before sending was `(-35.3632609, 149.1652298, 3.771 m)`; a later logged airborne position met the probe's target threshold. Captured `GLOBAL_POSITION_INT` telemetry came as close as approximately 0.11 m horizontally to the target while reporting 4.890 m relative altitude; peak captured relative altitude was 5.278 m. This is one simulation run and does not measure physical accuracy. Raw traffic, probe, logs, executable and decoded summary are in `sitl-evidence/command-ack-guided_flight_retry/`.

The Copter tests do not establish automatic GUIDED switching, UI behavior, packet-loss handling, or behavior with a physical vehicle. The retry used the explicit-target overload with automatic mode switching disabled.

## Plane mission-item experiment

The same original library was connected to a separate, disarmed source-built Plane simulator. The probe disabled automatic mode switching, submitted three zero-value inputs, sent a valid target while the Plane reported MANUAL, switched to GUIDED, and sent a second valid target. The raw capture contained two `MISSION_ITEM` packets, both waypoint command 16, `current=2`, sequence 0 and relative-altitude frame 3. The library used floating-point coordinate fields. The three zero-value calls did not add mission-item packets.

The first item received `MISSION_ACK` result 1 (`MAV_MISSION_ERROR`). The library logged `Guided Mode Failed` but returned from `setGuidedModeWP`; the probe continued. The second item, sent after a disarmed GUIDED heartbeat, received result 0 (`MAV_MISSION_ACCEPTED`). The final observed heartbeat was GUIDED and disarmed. Source confirms that guided mission items are dispatched separately from ordinary mission storage and acknowledged according to `handle_guided_request` (`libraries/GCS_MAVLink/GCS_Common.cpp:989`); Plane delegates to its active mode (`ArduPlane/GCS_MAVLink_Plane.cpp:465`).

`research-tools/summarize-plane-guided.py` decodes the retained traffic and checks the error/return sequence. Capture, probe source and executable, logs and summary are under `sitl-evidence/command-ack-plane_guided/`. The Plane simulator binary SHA-256 is `fc75bbfea710a9c41d863126b2f691976427a3263cacbb237ef5a72427b4187b`. This test observes acknowledgment, not movement, graphical behavior, automatic mode switching or physical flight.

## Plane acknowledgment loss

Two further disarmed GUIDED Plane runs sent the same guided waypoint using the original library. The relay dropped the first mission acknowledgment in one run and every mission acknowledgment in the other. In the first run, the library sent the item twice; the simulator produced two accepted acknowledgments, the second reached the library, and its stored guided target changed from zero to the encoded target. The call returned after approximately one second.

With every acknowledgment withheld, the library sent the item 11 times. The relay captured 11 accepted simulator acknowledgments and delivered none. After approximately ten seconds, the library logged `Timeout on read - setWP`, caught the exception inside `setGuidedModeWP`, and returned to the probe. Its stored guided target remained zero. Thus the caller's normal return alone did not distinguish this timeout from an acknowledged request in these runs. The accepted acknowledgments show how the simulator responded to each packet; they do not establish movement.

The matching source initializes ten retries and resends after timeout, then throws, while the outer guided wrapper catches exceptions (`MAVLinkInterface.cs:4058` and `:4420`). Exact elapsed time is specific to this run. `research-tools/summarize-plane-guided-loss.py` independently checks packet counts, results, hashes and the probe log. Source, binaries and directional captures are in `sitl-evidence/command-ack-plane_guided_drop_one/` and `sitl-evidence/command-ack-plane_guided_drop_all/`.

## Rejected target and mission readback

Another disarmed Plane run uploaded a two-item mission and read back its count and item 1. A guided target sent in MANUAL received `MAV_MISSION_ERROR`, which the library logged and caught; nevertheless, the library's cached `GuidedMode` changed from zero to the rejected target's encoded coordinates and 21 m altitude. The matching source assigns that cache after checking the acknowledgment destination but before returning its result (`MAVLinkInterface.cs:4095`). A later target in GUIDED received `MAV_MISSION_ACCEPTED` and replaced the cached target.

Mission count remained two and item 1 read back with the same latitude, longitude and altitude before either request, after rejection, and after acceptance. The raw capture independently contains all three count responses and three matching `MISSION_ITEM_INT` responses. This checks the count and one item, not the complete mission or its behavior in flight. The probe, traffic, and `state-summary.json` are in `sitl-evidence/command-ack-plane_guided_state/`; `research-tools/summarize-plane-guided-state.py` verifies them. Neither the displayed GUI state nor physical flight was tested.
