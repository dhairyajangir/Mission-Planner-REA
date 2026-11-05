# SupportProxy source and local tests

## Scope

SupportProxy is a separate ArduPilot organization repository, not part of the supplied firmware ZIP or Mission Planner. This analysis uses repository commit `21ca25286b2a0bcc25228e4d6bc20c5438abdcce`, its MAVLink submodule `a23652e3c7d1d7a94b1c2d354a13ce4858cd0996`, and nested pymavlink `19880422d451de4daba3fd96781076afb1cb889c`. The original files are under `supportproxy-source/`. This is selected source and test coverage, not a complete audit.

## Source map

The README describes a relay between a user-side ground station and a support engineer using separate configured ports; it lists UDP, TCP and WebSocket transports, optional TLS, signing and optional video. It also gives a Mission Planner GStreamer pipeline for the proxy's RTSP viewer (`README.md`, Video section). This is a documented integration; Mission Planner and video were not run together here.

`supportproxy.cpp` opens UDP and TCP sockets for the configured user and engineer ports (`:1188`), and manages per-entry child processes. `mavlink.cpp` parses MAVLink, checks signing state for keyed connections and handles `SETUP_SIGNING` locally (`:106`). Its sender strips signing for an unkeyed connection, signs for a keyed connection, and suppresses non-heartbeat messages before a signed engineer packet has been received (`:188`). `keydb_lib.py` manages the TDB configuration; `KeyEntry.set_passphrase` hashes the supplied passphrase with SHA-256 (`:344`). These are selected source paths, not a security assessment of the full server.

## Build and tests

The source built under Ubuntu 24.04 WSL using locally staged TDB libraries, headers and Python dependencies. No packages were installed system-wide. The generated binary SHA-256 is `24b53a1d9d64de4e79ce3499faea96f85c58392c567a8b2d05cdfad907e15bc8`. The Windows checkout produced CRLF shell scripts; the two build scripts were converted to LF before execution and their raw Git blob hashes were checked against the pinned commit. MAVLink header generation used the project's `--no-validate` option and printed enum warnings; this is not a claim that the generated dialect was fully validated.

The repository's `test_authentication.py` ran against disposable local TDB files: **13 passed**. Selected upstream UDP/UDP, TCP/TCP and mixed UDP/TCP tests returned **8 passed**. The tests use synthetic MAVLink peers and credentials, not Mission Planner or SITL. They check heartbeat and `SYSTEM_TIME` delivery for selected signed and unsigned connections. The UDP bad-key case also checks a proxy log message; the TCP bad-key test calls the scenario without asserting its returned message counts, so its pass alone does not prove rejection.

For the network tests a test-only `LD_PRELOAD` interposer changed IPv4 and IPv6 wildcard binds to loopback; a separate IPv4 socket probe confirmed that an attempted `0.0.0.0` bind became `127.0.0.1`. The repository binary itself was unchanged, but this altered binding environment limits the tests to local behavior. A fresh network namespace was unavailable. No process matching the built proxy path remained when checked after the tests. Test logs, dependency staging and the source of the interposer are preserved under `supportproxy-evidence/`, `supportproxy-deps/`, and `research-tools/`; `research-tools/summarize-supportproxy.py` records revision and artifact hashes.

No production credentials, public service, physical vehicle, actual remote client, WebSocket/TLS, video, full upstream test suite or Mission Planner connection was exercised. Earlier attempts to load the interposer from paths with spaces or an unavailable temporary path failed; those checks ran only a short-lived standalone socket probe, not the proxy tests.
