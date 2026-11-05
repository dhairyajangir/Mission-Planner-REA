# ArduPilot source map

Evidence: the user-supplied `ardupilot-master.zip`, SHA-256 `7edc50142718c3c98c1c679cf398ce7e258e29ec889ae65a53855b7a2bce931d`, extracted to `ardupilot-source/ardupilot-master`. Its archive comment identifies commit `72b238201f5ea3b556e3809b2ec704fcf701474a`; all 8,461 file contents match the corresponding blobs in the untruncated public Git tree for that commit. Reproducible results and the 14 pinned submodule Gitlinks are in `ardupilot-source/archive-provenance.json`. The original archive omitted Git history and submodule contents. Those 14 direct submodule sources and two nested submodule sources were subsequently retrieved at their pinned revisions and checked against their upstream blob IDs (`ardupilot-source/extracted-submodules.json`). A separate readback verified all 16,900 expected extracted blobs (`extracted-submodule-verification.json`). They are extracted source files, not initialized Git submodule checkouts. Two pymavlink symbolic links were stored as ordinary link-target text files in the Windows extraction; `source-symlink-inventory.json` records them, and the Linux temporary build recreates them as safe relative links. The vehicle version headers identify a 4.8.0-dev snapshot. This is an initial map, not a complete reverse engineering of ArduPilot.

`ArduPilot-Scripting-Trace.md` records a selected Lua startup and execution trace and a benign script run in source-built Copter SITL. `Mission-Transfer-Trace.md` records separate source paths and simulator observations for mission, fence and rally transfers.

## Organization

The ZIP contains 9,781 entries; approximately 6,997 are under `libraries`, 2,285 under `Tools`, and the rest include vehicle applications such as `ArduCopter`, `ArduPlane`, `Rover`, `ArduSub`, `Blimp` and `AntennaTracker`. These counts include directories and are not counts of distinct functions or features. The repository named in the request is one member of the broader [ArduPilot organization](https://github.com/ardupilot), which contains additional repositories; this map covers only the supplied archive.

| Area | Source starting point | What is established |
| --- | --- | --- |
| Vehicle entry points | `ArduCopter/Copter.cpp:971`, `ArduPlane/Plane.cpp:1155`, `Rover/Rover.cpp:560`, `ArduSub/Sub.cpp:490` | Each passes its vehicle object to the HAL entry mechanism. |
| Vehicle lifecycle | `libraries/AP_Vehicle/AP_Vehicle.cpp:315`, `:577` | Shared setup and loop methods. Each vehicle also has its own code and task table. |
| Scheduler | `libraries/AP_Scheduler/AP_Scheduler.cpp:191`, `:348`; `ArduCopter/Copter.cpp:113` | Scheduler runs registered tasks; Copter defines fast and timed tasks for its build. Compile-time options affect which tasks exist. |
| Hardware abstraction | `libraries/AP_HAL/` and implementation directories such as `libraries/AP_HAL_SITL/`, `libraries/AP_HAL_ChibiOS/` and `libraries/AP_HAL_Linux/` | Platform interfaces and backends. Hardware support must be assessed per board and build. |
| MAVLink | `libraries/GCS_MAVLink/GCS.h:174`, `libraries/GCS_MAVLink/GCS_Common.cpp:4308`, `:4387` | Ground-station protocol implementation and dispatch of parameter-read and mission-list messages. Vehicle-specific handlers are in each vehicle tree. |
| Parameters | `libraries/AP_Param/AP_Param.h:202` | Parameter system interface; storage and metadata behavior require tracing through its implementation and board configuration. |
| Mission engine | `libraries/AP_Mission/AP_Mission.h:62`, `libraries/GCS_MAVLink/MissionItemProtocol.cpp:69` | Mission storage/execution interfaces and MAVLink upload handling. |
| Attitude and navigation | `libraries/AP_AHRS/AP_AHRS.h:43`, `libraries/AP_NavEKF2/`, `libraries/AP_NavEKF3/` | Attitude and navigation subsystems; the active estimator depends on configuration and build. |
| Logging | `libraries/AP_Logger/AP_Logger.h:191`, `libraries/AP_Logger/` | Logging interfaces and backends. Actual logged messages depend on build and settings. |
| Simulation | `libraries/SITL/`, `libraries/AP_HAL_SITL/`, `Tools/autotest/` | Simulation models, SITL hardware backend and test tooling. The original ZIP omitted submodule contents; pinned files were recovered separately for the local build. |

## Observed protocol test

A local ArduCopter SITL binary was built from the verified archive and pinned source files in a temporary Linux directory. The build log is `sitl-evidence/archive-linux-copter-build.log` and the published binary is `sitl-evidence/archive-built/arducopter`, SHA-256 `646e5b5a2d294a200dfeee25558963ca50141b6dc5c08c1dd6880607e0c35a57`. The build used extracted submodule files and copied root Git metadata rather than a pristine recursive Git checkout. It was configured for SITL with submodule updates disabled; build success does not prove every firmware target builds.

Against that newly built binary, separate local tests received heartbeat, attitude, position, system status, a parameter response and mission count (`sitl-evidence/archive-copter-smoke/results.json`), and uploaded two integer mission items with matching waypoint readback (`sitl-evidence/archive-copter-mission/results.json`). These are test-client interactions, not physical flight or application-UI tests.

Plane, Rover and Sub SITL binaries were also built from the same archive snapshot and pinned sources. Each passed the standalone client's heartbeat, attitude, position, system status, `LOG_DISARMED` read and empty mission-list checks (`sitl-evidence/archive-{plane,rover,sub}-smoke/results.json`). The builds used the same extracted-source and copied-Git-metadata approach; they are not official releases or proof of other vehicle builds.

REA inspected ELF notes and native export tables for those three binaries and the later source-built Blimp and AntennaTracker binaries; all ten inspections reported complete coverage for their respective operations and matched the binary hashes (`sitl-evidence/archive-built-variants/rea-variant-manifest.json`). This is metadata and export-table coverage, not a disassembly or complete analysis of native functionality.

An official prebuilt ArduCopter 4.7.2 SITL binary was tested independently of this 4.8.0-dev source. The test client received heartbeat, attitude, global position, system status, a parameter response and mission count after requesting streams. See `sitl-evidence/smoke-run-2/results.json`. This confirms only the recorded simulator/client exchange. Mission Planner was not in the communication path.

The first mission upload attempt returned `MAV_MISSION_NO_SPACE`; the result is retained in `sitl-evidence/mission-roundtrip/results.json`. In the 4.8.0-dev source, `MissionItemProtocol.cpp:92` sends that result when the requested count exceeds `max_items()`. The prebuilt binary is a different version, so this source branch is a lead for investigation, not proof of the binary's exact cause. With a startup delay, an integer-item upload and exact coordinate readback passed in `sitl-evidence/mission-roundtrip-4/results.json`. Legacy float-item attempts accepted the upload but produced rounded coordinates; their failed exact-equality checks are preserved separately. No aircraft or Mission Planner application was involved.

## Outstanding coverage

Trace startup and message handling to each vehicle's mode logic, control loops, estimator, sensor drivers, storage and failsafes. `Vehicle-Mode-Failsafe-Trace.md` records a limited static examination of mode changes and selected failsafe paths. Inventory the numerous build options, board definitions, vehicle types and external components. The source-snapshot Copter SITL build succeeded; other vehicle builds require their own evidence. Test behavior against version-matched simulator builds and, separately, through Mission Planner. Do not infer physical-vehicle behavior from a simulator-only result.
# Searchable source snapshot

`integration-research/ardupilot-source-index.sqlite` indexes 7,309 UTF-8 files from the main repository tree at commit `72b238201f5ea3b556e3809b2ec704fcf701474a`. Each indexed worktree file matched its recorded Git blob hash during capture. The accompanying `ardupilot-source-index-summary.json` records the index hash and exclusions: 1,110 binary files, 39 files over 2 MiB, 3 non-UTF-8 files and 14 submodule links. Submodule contents and later source changes are outside this index.

From the project folder, `python research-tools/search-ardupilot-source.py EKF` prints up to 30 matching paths and excerpts. Search uses SQLite FTS5 token rules, so punctuation and underscores are token separators and a search is not a literal byte search. Use the source files for full context and line numbers.

The separate `integration-research/ardupilot-submodules-index.sqlite` indexes 15,494 UTF-8 files whose extracted bytes matched blob hashes from 16 saved pinned submodule trees. It excludes 1,200 binary files, 161 non-UTF-8 files, 43 files over 2 MiB and two symlink entries. The tree and source-manifest hashes are recorded in `ardupilot-submodules-index-summary.json`. Search with `python research-tools/search-ardupilot-source.py --submodules HEARTBEAT`. The indexes preserve the source snapshot; they do not establish runtime behavior or review every file.

